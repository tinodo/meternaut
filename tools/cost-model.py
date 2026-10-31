#!/usr/bin/env python3
"""Monthly cost model for Azure Cost in Action (standard library only).

Reads docs/design/cost/prices-snapshot.json (written by tools/fetch-prices.py from the
Azure Retail Prices API) and prices three scale scenarios.  Every meter is resolved by an
exact selector: a selector that matches zero meters, or more than one, stops the run, so a
changed price list can never silently change a number.

    python tools/cost-model.py                      # markdown report to stdout
    python tools/cost-model.py --json               # machine-readable
    python tools/cost-model.py --lines Team         # every line item of one scenario
    python tools/cost-model.py --update-doc docs/design/12-cost-and-finops.md
    python tools/cost-model.py --check  docs/design/12-cost-and-finops.md

All quantities below are *seeds*: assumptions to be replaced by measurements (spike S-COST-1).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "docs" / "design" / "cost" / "prices-snapshot.json"
HOURS = 730.0
DAYS = 30.4
BEGIN, END = "<!-- cost-model:begin -->", "<!-- cost-model:end -->"
REGION = "swedencentral"

# ---------------------------------------------------------------------------
# Scenarios (seeds).  Case-driven work scales with `cases`; clocks with `subs`.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "Pilot": dict(subs=5, resources=500, owners=5, cases=100, spend=20_000,
                  survey_calls=150, study_changes=40, exam_cases=600,
                  pe=20, la_gb=8, lake_gb=20, ledger_gb=1, ops_ru_m=20, ops_gb=2, search_units=1,
                  aca_vcpu_h=150, aca_req_m=1, dp_gb=50, own_subs=4),
    "Team": dict(subs=50, resources=10_000, owners=100, cases=1_000, spend=400_000,
                 survey_calls=1_500, study_changes=40, exam_cases=1_350,
                 pe=28, la_gb=40, lake_gb=300, ledger_gb=5, ops_ru_m=200, ops_gb=10, search_units=1,
                 aca_vcpu_h=600, aca_req_m=10, dp_gb=500, own_subs=5),
    "Enterprise": dict(subs=1000, resources=200_000, owners=2000, cases=20_000, spend=8_000_000,
                       survey_calls=30_000, study_changes=40, exam_cases=2_700,
                       pe=30, la_gb=400, lake_gb=4_000, ledger_gb=40, ops_ru_m=1_500, ops_gb=100, search_units=2,
                       aca_vcpu_h=3_000, aca_req_m=100, dp_gb=5_000, own_subs=8),
}

# Token workloads per *case* (W4).  calls, input tokens, cached share of input, cache-write tokens, output tokens.
CASE_WORK = [
    ("Detective", "reason", dict(calls=10, tin=15_000, cached=0.70, cw=6_000, tout=1_500)),
    ("Skeptic", "judge", dict(calls=4, tin=12_000, cached=0.00, cw=0, tout=1_000)),
    ("Economist", "reason", dict(calls=4, tin=10_000, cached=0.60, cw=5_000, tout=1_000)),
    ("Diplomat", "reason", dict(calls=2, tin=6_000, cached=0.50, cw=3_000, tout=800)),
    ("Triage", "luna", dict(calls=6, tin=3_000, cached=0.50, cw=1_500, tout=300)),
]
HOSTED_H_PER_CASE = 0.45      # active session hours per case, including a 2-minute idle timeout per session
SANDBOX_H_PER_CASE = 0.0      # sandbox hours: typed query tools are preferred (05 section 5)

# Manual figures that are not in the price API.  Each names its source.
MANUAL = {
    "logic_app_ws1": (158.0, "research/citadel.md section 7 (Logic App Standard WS1, EUR per month)"),
    "hub_misc": (18.0, "research/citadel.md section 7 (storage and logging of the hub, EUR per month)"),
    "front_door_premium": (290.39, "research/security-and-compliance.md W1 (EUR per month, base)"),
    "confidential_ledger": (103.0, "research/features-07.md F7 (Standard instance, EUR per month, West Europe)"),
    "agent365_user_usd": (15.0, "research/security-and-compliance.md D4 (USD per user per month, list)"),
    "defender_ai_per_1k_tokens": (0.000704, "research/security-and-compliance.md D3 (EUR per 1K tokens)"),
    "adx_devtest": (105.0, "research/options-analysis.md section 2b (about USD 120 per month, EUR)"),
}


class Prices:
    def __init__(self, path: Path):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.meters = d["meters"]
        self.fx = float(d["fx"]["eurPerUsd"])
        self.generated = d["generatedAt"]
        self.used: dict[str, tuple[float, str]] = {}

    def eur(self, m: dict) -> float:
        p = m["prices"]
        return float(p["EUR"]) if "EUR" in p else float(p["USD"]) * self.fx

    def get(self, service: str, region: str = REGION, product: str | None = None, sku: str | None = None,
            meter: str | None = None, pick: str = "only") -> float:
        hits = []
        for m in self.meters:
            if m["service"] != service or m["priceType"] != "Consumption":
                continue
            if region is not None and m["region"] != region:
                continue
            if product is not None and not re.fullmatch(product, m["product"]):
                continue
            if sku is not None and not re.fullmatch(sku, m["sku"]):
                continue
            if meter is not None and not re.fullmatch(meter, m["meter"]):
                continue
            hits.append(m)
        sel = f"{service}|{region}|{product}|{sku}|{meter}"
        if not hits:
            raise LookupError(f"no meter for selector {sel}")
        vals = sorted({self.eur(m) for m in hits})
        if len(vals) > 1 and pick == "only":
            raise LookupError(f"{len(hits)} meters ({vals}) for selector {sel}; add pick='max' or narrow it")
        v = vals[-1] if pick == "max" else vals[0] if pick == "min" else vals[0]
        self.used[sel] = (v, hits[0]["unitOfMeasure"])
        return v


def per_m(price_1k: float) -> float:
    return price_1k * 1000.0


class Model:
    def __init__(self, prices: Prices):
        self.p = prices

    # -- token prices (EUR per 1M tokens) ---------------------------------
    def gpt6(self, family: str, zone: str, svc_class: str = "Std") -> dict:
        g = lambda kind: self.p.get("Foundry Models", product="Azure OpenAI GPT6",
                                    sku=rf"{re.escape(family)} ShortCo {kind} {svc_class} {zone}", pick="min")
        out = dict(inp=g("Inp"), out=g("Opt"))
        if svc_class == "Std":
            out["cd"], out["cw"] = g("Cd Inp"), g("Cd Wr")
        else:
            out["cd"], out["cw"] = g("Cd Inp"), g("Cd Wr")
        return out

    def mistral_large3(self, zone: str) -> dict:
        s = "Dzone" if zone == "DZ" else "glbl"
        i = self.p.get("Foundry Models", product="Azure Mistral Models", sku=rf"Large 3 Inp {s}", pick="min")
        o = self.p.get("Foundry Models", product="Azure Mistral Models", sku=rf"Large 3 Outp {s}", pick="min")
        return dict(inp=per_m(i), out=per_m(o), cd=per_m(i), cw=0.0)

    def alias(self, alias: str, zone: str, svc_class: str = "Std") -> dict:
        if alias == "reason":
            return self.gpt6("6.1-sol", zone, svc_class)
        if alias == "luna":
            return self.gpt6("6-luna", zone, svc_class)
        if alias == "judge":
            return self.mistral_large3(zone)
        raise KeyError(alias)

    @staticmethod
    def tokens_cost(price: dict, calls: float, tin: float, cached: float, cw: float, tout: float) -> float:
        per_call = (tin * (1 - cached) * price["inp"] + tin * cached * price["cd"]
                    + cw * price["cw"] + tout * price["out"]) / 1e6
        return calls * per_call

    def case_cost(self, zone: str = "DZ", svc_class: str = "Std", detail: bool = False):
        total, rows = 0.0, []
        for role, alias, w in CASE_WORK:
            c = self.tokens_cost(self.alias(alias, zone, svc_class), **w)
            total += c
            rows.append((role, alias, c))
        return (total, rows) if detail else total

    # -- one scenario ------------------------------------------------------
    def scenario(self, name: str, hub: str = "shared") -> dict:
        s = SCENARIOS[name]
        P, L = self.p, []

        def add(group: str, label: str, eur: float, note: str = "") -> None:
            L.append(dict(group=group, label=label, eur=round(eur, 2), note=note))

        # tokens -----------------------------------------------------------
        case_eu, _ = self.case_cost("DZ", "Std", detail=True)
        add("Tokens", "Cases (W4) on the EU Data Zone", s["cases"] * case_eu, f"{s['cases']} cases at EUR {case_eu:.3f} each")
        feed_items = 150 * 30
        luna_gl = self.gpt6("6-luna", "Gl")
        add("Tokens", "Watch (W1): triage of the release feed", self.tokens_cost(luna_gl, feed_items, 1_500, 0.5, 0, 100),
            "public data, Global")
        sol_gl = self.gpt6("6.1-sol", "Gl")
        add("Tokens", "Study (W2): Scholar, Cartographer, Librarian",
            s["study_changes"] * (self.tokens_cost(sol_gl, 12, 20_000, 0.5, 6_000, 2_000)
                                  + self.tokens_cost(sol_gl, 8, 15_000, 0.5, 4_000, 1_500)),
            "public data, Global Standard")
        luna_eu, sol_eu = self.gpt6("6-luna", "DZ"), self.gpt6("6.1-sol", "DZ")
        calls = s["survey_calls"]
        add("Tokens", "Survey (W3): Surveyor on changes",
            self.tokens_cost(luna_eu, 0.8 * calls, 8_000, 0.5, 2_000, 600)
            + self.tokens_cost(sol_eu, 0.2 * calls, 8_000, 0.5, 2_000, 600), "80% Luna, 20% Sol, EU Data Zone")
        dream_calls = 30 * (5 + s["cases"] / 200.0)
        add("Tokens", "Dream (W7): nightly consolidation", self.tokens_cost(sol_eu, dream_calls, 20_000, 0.5, 5_000, 2_000),
            "estate lessons, EU Data Zone (flex is Global only)")
        ex_case, _ = self.case_cost("Gl", "Flex", detail=True)
        add("Tokens", "Exams and release gates (W8) on synthetic estates", s["exam_cases"] * ex_case * 1.3,
            "Flex, Global, plus 30% for judges")
        embed = P.get("Foundry Models", product="Azure OpenAI", sku="text-embedding-3-large-regional") * 1000.0
        add("Tokens", "Embeddings (Atlas releases and retrieval)",
            (5_000_000 * 4 + s["cases"] * 50 * 300) / 1e6 * embed, "weekly index rebuild plus retrieval")
        cs = P.get("Foundry Tools", product="Content Safety", sku="Standard", meter="Standard Text Records")
        records = s["cases"] * 40 + feed_items + calls
        add("Tokens", "Content safety screening of untrusted text", max(0.0, records - 5_000) / 1000.0 * cs,
            f"{records:,.0f} records, 5,000 free")

        # compute ------------------------------------------------------------
        hv = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted vCPU Usage")
        hm = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted Memory Usage")
        hosted_h = (s["cases"] + s["exam_cases"]) * HOSTED_H_PER_CASE + s["study_changes"] * 1.0 + calls * 5 / 60.0 + 30 * 0.5
        add("Compute", "Hosted agents: active session hours", hosted_h * (hv * 1.0 + hm * 2.0), f"{hosted_h:,.0f} h at 1 vCPU and 2 GiB")
        vcpu_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard vCPU Active Usage")
        mem_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Memory Active Usage")
        req = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Requests")
        grant_v, grant_m, grant_r = 180_000 * s["own_subs"] / 4, 360_000 * s["own_subs"] / 4, 2.0 * s["own_subs"] / 4
        vcpu_sec, gib_sec = s["aca_vcpu_h"] * 3600, s["aca_vcpu_h"] * 3600 * 2
        add("Compute", "Container Apps: tool services, spine jobs, adapters",
            max(0, vcpu_sec - grant_v) * vcpu_s + max(0, gib_sec - grant_m) * mem_s + max(0, s["aca_req_m"] - grant_r) * req,
            f"{s['aca_vcpu_h']} vCPU-hours, 2 GiB each, after the free grants")

        # data and observability ----------------------------------------------
        srch = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Basic", meter="Basic Unit")
        add("Data", "AI Search Basic (Foundry standard setup and the Atlas)", s["search_units"] * srch * HOURS, f"{s['search_units']} unit(s)")
        ru = P.get("Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs", meter="1M RUs")
        st = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="Data Stored")
        add("Data", "Cosmos DB serverless: operational store and Foundry's own", (s["ops_ru_m"] + 20) * ru + (s["ops_gb"] + 5) * st,
            f"{s['ops_ru_m']} M request units and {s['ops_gb']} GB, plus 20 M and 5 GB for Foundry")
        cool = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Cool ZRS", meter="Cool ZRS Data Stored", pick="max")
        hot = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Hot ZRS", meter="Hot ZRS Data Stored", pick="max")
        add("Data", "Cost lake (Cool ZRS) and ledger (Hot ZRS)", s["lake_gb"] * cool + s["ledger_gb"] * hot * 2, f"{s['lake_gb']} GB lake, {s['ledger_gb']} GB ledger x2 for redundancy")
        acr_day = P.get("Container Registry", product="Container Registry", sku="Premium", meter="Premium Registry Unit")
        add("Data", "Container Registry Premium (private pull)", acr_day * DAYS, "one registry")
        pe_h = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard", meter="Standard Private Endpoint")
        pe_gb = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard",
                      meter="Standard Data Processed - Egress", pick="max")
        add("Network", "Private endpoints (hourly)", s["pe"] * pe_h * HOURS, f"{s['pe']} endpoints")
        add("Network", "Private endpoint data processed", s["dp_gb"] * pe_gb * 2, f"{s['dp_gb']} GB in and out")
        la_a = P.get("Log Analytics", product="Log Analytics", sku="Analytics Logs", meter="Analytics Logs Data Ingestion", pick="max")
        la_b = P.get("Azure Monitor", product="Azure Monitor", sku="Basic Logs", meter="Basic Logs Data Ingestion")
        la_x = P.get("Azure Monitor", product="Azure Monitor", sku="Auxiliary Logs", meter="Auxiliary Logs Data Ingestion")
        gb = s["la_gb"]
        add("Observability", "Log Analytics ingestion (30% analytics, 50% basic, 20% auxiliary)",
            max(0.0, 0.3 * gb - 5) * la_a + 0.5 * gb * la_b + 0.2 * gb * la_x, f"{gb} GB, 5 GB free")
        drm = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Resource Manager", sku="Per node Std", meter="Per node Std Node")
        dkv = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Key Vault", sku="Per node Std", meter="Per node Std Node")
        add("Security", "Defender for Resource Manager and Key Vault (default tier)", s["own_subs"] * drm * HOURS + 3 * dkv * HOURS,
            f"{s['own_subs']} subscriptions, 3 vaults")

        # hub ----------------------------------------------------------------------
        if hub == "shared":
            add("Hub", "Shared Citadel hub: nothing fixed is ours", 0.0, "our share is tokens and calls")
        else:
            apim_dev = P.get("API Management", product="API Management", sku="Developer", meter="Developer Unit")
            apim_std = P.get("API Management", product="API Management", sku="Standard v2", meter="Standard v2 Unit")
            eh = P.get("Event Hubs", product="Event Hubs", sku="Standard", meter="Standard Throughput Unit")
            cosmos100 = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="100 RU/s")
            apim = apim_dev if hub == "own-small" else apim_std
            add("Hub", "Own hub: API Management " + ("Developer" if hub == "own-small" else "Standard v2"), apim * HOURS, "Sweden Central price")
            add("Hub", "Own hub: usage pipeline (Event Hubs, Cosmos 7 x 400 RU/s, Logic App WS1)",
                eh * HOURS + 28 * cosmos100 * HOURS + MANUAL["logic_app_ws1"][0], "Logic App figure from the Citadel research")
            add("Hub", "Own hub: endpoints, storage, logging", 9 * pe_h * HOURS + MANUAL["hub_misc"][0], "9 private endpoints")
        groups: dict[str, float] = {}
        for r in L:
            groups[r["group"]] = groups.get(r["group"], 0.0) + r["eur"]
        total = sum(groups.values())
        return dict(name=name, hub=hub, lines=L, groups={k: round(v, 2) for k, v in groups.items()}, total=round(total, 2),
                    per_case=round(total / s["cases"], 2), per_sub=round(total / s["subs"], 2),
                    breakeven_pct=round(100.0 * total / s["spend"], 2), params=s)

    def optional(self) -> list[tuple[str, float, str]]:
        au = self.p.get("Foundry Tools", product="Azure Agent Unit", sku="SRE", meter="SRE Agent Unit")
        return [
            ("Azure SRE Agent, always on (4 units an hour)", 4 * HOURS * au, "price API"),
            ("Agent 365 for 5 sponsors (list)", 5 * MANUAL["agent365_user_usd"][0] * self.p.fx, MANUAL["agent365_user_usd"][1]),
            ("Defender for AI Services at 100 M tokens", 100_000 * MANUAL["defender_ai_per_1k_tokens"][0], MANUAL["defender_ai_per_1k_tokens"][1]),
            ("Front Door Premium, base only", MANUAL["front_door_premium"][0], MANUAL["front_door_premium"][1]),
            ("Confidential Ledger, smallest standard instance", MANUAL["confidential_ledger"][0], MANUAL["confidential_ledger"][1]),
            ("Azure Data Explorer Dev/Test, if kept on", MANUAL["adx_devtest"][0], MANUAL["adx_devtest"][1]),
            ("Azure Firewall Standard, if the landing zone has none",
             self.p.get("Azure Firewall", product="Azure Firewall", sku="Standard", meter="Standard Deployment") * HOURS, "price API, deployment hour only"),
        ]

    def sensitivity(self) -> list[tuple[str, float]]:
        base = self.case_cost("DZ", "Std")
        gl = self.case_cost("Gl", "Std")
        # Terra for the investigation tier
        def terra(zone: str) -> float:
            g = lambda kind: self.p.get("Foundry Models", product="Azure OpenAI GPT6", sku=rf"61 terra ShortCo {kind} Std {zone}", pick="min") \
                if kind != "Opt" else self.p.get("Foundry Models", product="Azure OpenAI GPT6", sku=rf"61 terra ShortCo Opt [Ss]td {zone}", pick="min")
            price = dict(inp=g("Inp"), out=g("Opt"), cd=g("Cd Inp"), cw=g("Cd Wr"))
            tot = 0.0
            for role, alias, w in CASE_WORK:
                pr = price if alias == "reason" else self.alias(alias, zone)
                tot += self.tokens_cost(pr, **w)
            return tot
        nocache = 0.0
        for role, alias, w in CASE_WORK:
            w2 = dict(w, cached=0.0, cw=0)
            nocache += self.tokens_cost(self.alias(alias, "DZ"), **w2)
        return [("Baseline: one case on the EU Data Zone", base),
                ("The same case on Global (not allowed for estate data: the price of residency)", gl),
                ("Investigation tier on Terra instead of Sol", terra("DZ")),
                ("No prompt caching", nocache)]


def fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"


def report(model: Model) -> str:
    out = ["| Scenario | Fixed and platform | Compute | Tokens | **Total, shared hub** | Own hub, small | Own hub, medium | Per case | Per subscription | Break-even share of monitored spend |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for n in SCENARIOS:
        a = model.scenario(n, "shared")
        b = model.scenario(n, "own-small")
        c = model.scenario(n, "own-medium")
        g = a["groups"]
        fixed = sum(v for k, v in g.items() if k not in ("Tokens", "Compute"))
        out.append(f"| **{n}** | €{fmt(fixed)} | €{fmt(g['Compute'])} | €{fmt(g['Tokens'])} | **€{fmt(a['total'])}** | €{fmt(b['total'])} | "
                   f"€{fmt(c['total'])} | €{a['per_case']:.2f} | €{a['per_sub']:.2f} | {a['breakeven_pct']:.2f} % |")
        detail.append(a)
    out.append("")
    out.append("Monthly euros. *Fixed and platform* is data, network, observability and security; *shared hub* means the Citadel hub belongs to the landing zone. "
               "Break-even is the share of monitored cloud spend the system must verifiably save to cover its own cost "
               "(monitored spend: " + ", ".join(f"{k} €{v['spend']:,}" for k, v in SCENARIOS.items()) + " a month).")
    out.append("")
    out.append("**Where the tokens go** (shared hub):")
    out.append("")
    labels = [r["label"] for r in detail[0]["lines"] if r["group"] == "Tokens"]
    out.append("| Workload | " + " | ".join(SCENARIOS) + " |")
    out.append("|---|" + "---|" * len(SCENARIOS))
    for lab in labels:
        vals = [next(r["eur"] for r in d["lines"] if r["label"] == lab) for d in detail]
        out.append(f"| {lab} | " + " | ".join(f"€{fmt(v)}" for v in vals) + " |")
    out.append("")
    out.append("**One case, on the strongest tier, by role** (EU Data Zone):")
    out.append("")
    tot, rows = model.case_cost("DZ", "Std", detail=True)
    out.append("| Role | Alias | € per case |")
    out.append("|---|---|---|")
    for role, alias, c in rows:
        out.append(f"| {role} | `acia-{ {'reason':'reason','luna':'triage','judge':'judge-eu'}[alias] }` | {c:.3f} |")
    out.append(f"| **Total** | | **{tot:.3f}** |")
    out.append("")
    out.append("**Sensitivity** (one case):")
    out.append("")
    out.append("| Variant | € per case |")
    out.append("|---|---|")
    for lab, v in model.sensitivity():
        out.append(f"| {lab} | {v:.3f} |")
    out.append("")
    out.append("**Optional modules, off by default** (monthly euros, standalone):")
    out.append("")
    out.append("| Module | € a month | Basis |")
    out.append("|---|---|---|")
    for lab, v, src in model.optional():
        out.append(f"| {lab} | {fmt(v)} | {src} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lines", metavar="SCENARIO")
    ap.add_argument("--hub", default="shared", choices=["shared", "own-small", "own-medium"])
    ap.add_argument("--update-doc", metavar="FILE")
    ap.add_argument("--check", metavar="FILE")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    prices = Prices(SNAP)
    model = Model(prices)
    if args.lines:
        d = model.scenario(args.lines, args.hub)
        for r in d["lines"]:
            print(f"{r['group']:<14} {r['label']:<75} {r['eur']:>12,.2f}   {r['note']}")
        print(f"{'TOTAL':<90} {d['total']:>12,.2f}")
        return 0
    if args.json:
        print(json.dumps({n: model.scenario(n, args.hub) for n in SCENARIOS}, indent=2))
        return 0
    block = (f"{BEGIN}\n_Generated by `tools/cost-model.py` from `docs/design/cost/prices-snapshot.json` "
             f"(prices retrieved {prices.generated}; EUR per USD {prices.fx:.5f}). Do not edit by hand._\n\n"
             f"{report(model)}\n{END}")
    if args.update_doc or args.check:
        path = Path(args.update_doc or args.check)
        text = path.read_text(encoding="utf-8")
        m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), text, re.S)
        if not m:
            print(f"{path}: markers not found", file=sys.stderr)
            return 2
        if args.check:
            if m.group(0) != block:
                print(f"{path}: generated block is stale; run tools/cost-model.py --update-doc {path}", file=sys.stderr)
                return 1
            print(f"{path}: cost block is current")
            return 0
        path.write_text(text[: m.start()] + block + text[m.end():], encoding="utf-8")
        print(f"updated {path}")
        return 0
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
