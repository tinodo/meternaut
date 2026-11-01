#!/usr/bin/env python3
"""Monthly cost model for Azure Cost in Action (standard library only).

Reads docs/design/cost/prices-snapshot.json (Azure Retail Prices API, EUR, Sweden Central, 730 h a
month; written by tools/fetch-prices.py) and prices three scenarios. Every meter is resolved by an
exact selector: a selector that matches no meter, or several meters with different prices, stops the
run, so a changed price list can never silently change a number.

    python tools/cost-model.py                          # markdown report to stdout
    python tools/cost-model.py --json                   # machine-readable
    python tools/cost-model.py --lines Pilot            # every line item of one scenario
    python tools/cost-model.py --update-doc docs/design/10-cost-and-finops.md
    python tools/cost-model.py --check docs/design/10-cost-and-finops.md     # fails when the generated block is stale
    python tools/cost-model.py --self-test              # negative fixtures: each defect above must be caught

Volumes below are scenario parameters and seeds (calls per case, tokens per call, minutes per
session). They are replaced by measurements in proof point P10; the report says so.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "docs" / "design" / "cost" / "prices-snapshot.json"
HOURS = 730.0
DAYS = 30.4
REGION = "swedencentral"
BEGIN, END = "<!-- cost-model:begin -->", "<!-- cost-model:end -->"

# Scenario parameters (sizing only). `cases` = cases that reach an owner each month.
SCENARIOS = {
    "Pilot": dict(subs=5, resources=500, owners=10, cases=20, spend=50_000, study_docs_day=40,
                  eval_changes=8, eval_releases=2, safety_runs=1, la_gb=8, ops_gb=2, lake_gb=2, ledger_gb=1,
                  storage_ops_10k=10, analysis_gb_s=20_000, kv_ops_10k=20, dp_gb=20, search_units=1),
    "Team": dict(subs=50, resources=10_000, owners=100, cases=200, spend=1_000_000, study_docs_day=80,
                 eval_changes=12, eval_releases=3, safety_runs=1, la_gb=60, ops_gb=10, lake_gb=40, ledger_gb=5,
                 storage_ops_10k=60, analysis_gb_s=300_000, kv_ops_10k=100, dp_gb=150, search_units=2),
    "Enterprise": dict(subs=1000, resources=200_000, owners=1500, cases=2000, spend=25_000_000, study_docs_day=150,
                       eval_changes=20, eval_releases=4, safety_runs=2, la_gb=600, ops_gb=100, lake_gb=800,
                       ledger_gb=50, storage_ops_10k=600, analysis_gb_s=3_000_000, kv_ops_10k=500, dp_gb=1500,
                       search_units=3),
}

# One case, agent by agent: (agent, calls, input tokens per call, cached prefix per call, output tokens, alias, share of cases)
CASE_MIX = [
    ("Detective", 20, 30_000, 18_000, 1_500, "reason", 1.0),
    ("Skeptic", 6, 15_000, 8_000, 1_000, "judge", 1.0),
    ("Economist", 5, 15_000, 8_000, 1_500, "reason", 1.0),
    ("Diplomat", 6, 8_000, 4_000, 1_000, "reason", 1.0),
    ("Engineer", 4, 10_000, 5_000, 1_500, "reason", 0.5),
    ("Auditor", 2, 5_000, 2_000, 600, "triage", 1.0),
    ("Surveyor", 3, 6_000, 3_000, 600, "triage", 1.0),
]
LEADS_PER_CASE = 10
WATCH_CALL = (3_000, 1_500, 300)                 # input, cached prefix, output tokens of one triage call
STUDY_DOC = dict(triage=(8_000, 0, 500), relevant=0.15, decode=(30_000, 10_000, 3_000), challenge=(10_000, 0, 1_000),
                 curate=(10_000, 0, 1_500), accepted=0.3)
ESTATE_CALLS_PER_RESOURCE = 0.8                   # Surveyor calls a month per resource (rules first, model for the rest)
ESTATE_CALL = (5_000, 2_000, 500)
COMPONENT_CASES, COMPONENT_CALLS = 40, (4, 20_000, 12_000, 1_500)     # one agent, canned inputs
E2E_CASES = 30                                    # full cases on synthetic estates per release
JUDGE_CALL = (20_000, 0, 1_000)                   # one judged run
SAMPLE_SHARE = 0.05                               # production cases scored by evaluators
SAFETY_ATTACKS = 1_000
SAFETY_ROUND_TRIP = dict(target=(3_000, 0, 600), attacker=(1_500, 0, 400), evaluator=(3_000, 0, 200))
DEV_SMOKE_CALLS, DEV_SMOKE_TOKENS = 2_400, 1_000
EMBED_TOKENS_M = 3.0                              # Atlas re-embedding and incremental updates, millions of tokens a month

# Sessions and runtime (hosted agents: 0.5 vCPU, 1 GiB; five hosted agents, idle timeout 2 minutes, one session id per workflow run)
HOSTED_VCPU, HOSTED_GIB = 0.5, 1.0
CASE_HOSTED_H = 1.4                               # active time plus idle-timeout tails of one case across the five hosted agents
WATCH_RUN_MIN, WATCH_RUNS = 4.0, 730
STUDY_DOC_MIN = 3.5
ESTATE_CALL_MIN = 0.4
COMPONENT_CASE_H, E2E_CASE_H = 0.3, CASE_HOSTED_H
EXEC_PER_CASE, FN_REPLAY, FN_GB_S_PER_EXEC = 150, 1.3, 2.0
FN_INSTANCE_GB, FN_READY_SHARE = 2, 0.8            # always-ready instance size; share of orchestration work it serves
TOOL_CALLS_PER_CASE, TOOL_CALLS_PER_ESTATE_CALL = 100, 3     # tool-service executions (read tools, plan, drafts) on the same Functions plan
FN_FREE_GB_S, FN_FREE_EXEC = 100_000, 250_000
PE_OPERATE = 8                                    # Foundry account, Search, Cosmos, audit Storage, platform Storage (blob, queue, table), Key Vault; the monitor scope belongs to the landing zone
PE_BYO_FOUNDRY = 2                                # Foundry's own Cosmos and Storage, only if the adopter wants agent data in its own resources
BYO_FOUNDRY_GB = 5                                # agent files and state in those two accounts
SEARCH_QUERIES_PER_CASE, SEARCH_FREE_QUERIES = 20, 1_000
COSMOS_RU_M_PER_CASE, COSMOS_RU_M_PER_RESOURCE = 0.05, 0.0002
CS_RECORDS_PER_CASE, CS_RECORDS_PER_DOC = 100, 30
PII_RECORDS_PER_CALL, PII_SURVEYOR_SHARE = 10, 0.05
OWNER_MIN_PER_CASE, REVIEW_MIN_PER_ATLAS_CHANGE, CLAIMS_PER_CHANGE = 5, 10, 5
LA_SPLIT = dict(analytics=0.3, basic=0.5, auxiliary=0.2)

# Figures that are not in the price API. Each names its source.
MANUAL = {
    "language_pii_per_1k": (0.88, "Citadel research digest section 7 (Azure AI Language PII, EUR per 1,000 records; falls at volume, UNVERIFIED)"),
    "durable_storage_env": (4.0, "estimate: about 1.3 M queue-polling transactions a month plus tables and blobs; queue and table meters are not in the snapshot"),
    "logic_app_ws1": (158.0, "Citadel research digest section 7 (Logic App Standard WS1, EUR per month)"),
    "hub_misc": (18.0, "Citadel research digest section 7 (storage and logging of the hub, EUR per month)"),
    "defender_ai_per_1k_tokens": (0.000704, "security research digest D3 (Defender for AI Services, EUR per 1,000 tokens)"),
}

DEFAULT_KNOBS = dict(estate_zone="DZ", token_scale=1.0, cache=True, flex=True, la_split="tiered", own_hub=False,
                     defender_ai=False, extra_search_units=0, foundry_byo_data=False, always_ready=1)
SENSITIVITIES = [
    ("Global Standard for estate data instead of Data Zone", dict(estate_zone="Gl")),
    ("Investigations twice as long (twice the tokens per case)", dict(token_scale=2.0)),
    ("Prompt caching does not hit", dict(cache=False)),
    ("Flex (preview) not used: study and evaluation on Global Standard", dict(flex=False)),
    ("Every log table on the Analytics plan", dict(la_split="analytics")),
    ("One more AI Search unit (replica)", dict(extra_search_units=1)),
    ("No always-ready Functions instance (cold starts accepted)", dict(always_ready=0)),
    ("Agent data in the adopter's own Cosmos DB and Storage (Foundry bring-your-own data)", dict(foundry_byo_data=True)),
    ("Defender for AI Services on every model call", dict(defender_ai=True)),
    ("Own small governance hub (only if the organisation has none)", dict(own_hub=True)),
]


class Prices:
    def __init__(self, path: Path):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.meters = d["meters"]
        self.fx = float(d["fx"]["eurPerUsd"])
        self.generated = d["generatedAt"]
        self.used: dict[str, tuple[float, str]] = {}
        self._cache: dict[tuple, float] = {}

    def eur(self, m: dict) -> float:
        p = m["prices"]
        return float(p["EUR"]) if "EUR" in p else float(p["USD"]) * self.fx

    def get(self, service: str, region: str = REGION, product: str | None = None, sku: str | None = None,
            meter: str | None = None, pick: str = "only") -> float:
        key = (service, region, product, sku, meter, pick)
        if key in self._cache:
            return self._cache[key]
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
            raise LookupError(f"{len(hits)} meters ({vals}) for selector {sel}; narrow it or pick='max'/'min'")
        v = vals[-1] if pick == "max" else vals[0]
        self.used[sel] = (v, hits[0]["unitOfMeasure"])
        self._cache[key] = v
        return v


def fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"


class Model:
    def __init__(self, prices: Prices, **knobs):
        self.p = prices
        unknown = set(knobs) - set(DEFAULT_KNOBS)
        if unknown:
            raise KeyError(f"unknown knob {sorted(unknown)}")
        self.k = {**DEFAULT_KNOBS, **knobs}

    # -- tokens (EUR per 1M tokens) ------------------------------------------
    def price(self, alias: str, zone: str, tier: str) -> dict:
        P = self.p
        if alias == "judge":                     # a different model family: Mistral Large 3 (per 1K tokens in the API)
            s = "Dzone" if zone == "DZ" else "glbl"
            i = P.get("Foundry Models", product="Azure Mistral Models", sku=rf"Large 3 Inp {s}", pick="min") * 1000
            o = P.get("Foundry Models", product="Azure Mistral Models", sku=rf"Large 3 Outp {s}", pick="min") * 1000
            return dict(inp=i, out=o, cd=i, cw=0.0)
        fam = {"reason": "6.1-sol", "triage": "6-luna"}[alias]
        cls = "Flex" if tier == "Flex" else "Std"
        z = "Gl" if cls == "Flex" else zone
        g = lambda kind: P.get("Foundry Models", product="Azure OpenAI GPT6",
                               sku=rf"{re.escape(fam)} ShortCo {kind} {cls} {z}", pick="min")
        return dict(inp=g("Inp"), out=g("Opt"), cd=g("Cd Inp"), cw=g("Cd Wr"))

    def token_eur(self, alias: str, scope: str, tier: str, calls: float, tin: float, prefix: float, tout: float,
                  sessions: float = 1.0) -> float:
        """Cost of `calls` calls. A cached prefix is written once per session and read on the other calls."""
        zone = self.k["estate_zone"] if scope == "estate" else "Gl"
        pr = self.price(alias, zone, tier if self.k["flex"] or tier != "Flex" else "Std")
        prefix = min(prefix, tin) if self.k["cache"] else 0.0
        writes = min(calls, sessions)
        reads = calls - writes
        plain = calls * (tin - prefix) * pr["inp"]
        return (plain + writes * prefix * pr["cw"] + reads * prefix * pr["cd"] + calls * tout * pr["out"]) / 1e6

    # -- one scenario ---------------------------------------------------------
    def scenario(self, name: str) -> dict:
        s, P, k = SCENARIOS[name], self.p, self.k
        L: list[dict] = []

        def add(profile: str, group: str, label: str, eur: float, note: str, idle: float = 0.0) -> None:
            L.append(dict(profile=profile, group=group, label=label, eur=round(eur, 2), idle=round(eur * idle, 2), note=note))

        cases, scale = s["cases"], k["token_scale"]
        docs_month = s["study_docs_day"] * DAYS
        estate_calls = s["resources"] * ESTATE_CALLS_PER_RESOURCE

        # ---- Operate profile: models ----------------------------------------
        case_tokens_in = sum(c * i * sh for _, c, i, _, _, _, sh in CASE_MIX)
        case_tokens_out = sum(c * o * sh for _, c, _, _, o, _, sh in CASE_MIX)
        case_eur = sum(self.token_eur(al, "estate", "Std", cases * c * sh * scale, i, pf, o, sessions=cases * sh * scale)
                       for _, c, i, pf, o, al, sh in CASE_MIX)
        add("Operate", "Models", "Cases: the agents' tokens", case_eur,
            f"{cases} cases x {case_tokens_in/1000:,.0f}k input and {case_tokens_out/1000:,.0f}k output tokens (seed, P10); Detective, Economist, Diplomat, Engineer on `reason`, Skeptic on `judge`, others on `triage`")
        leads = cases * LEADS_PER_CASE
        add("Operate", "Models", "Watch: triage of leads", self.token_eur("triage", "estate", "Std", leads, *WATCH_CALL, sessions=30),
            f"{leads:,} leads, one small-model call each")
        d = STUDY_DOC
        rel = docs_month * d["relevant"]
        study = (self.token_eur("triage", "public", "Flex", docs_month, *d["triage"], sessions=30)
                 + self.token_eur("reason", "public", "Flex", rel, *d["decode"], sessions=30)
                 + self.token_eur("judge", "public", "Std", rel, *d["challenge"])
                 + self.token_eur("reason", "public", "Flex", rel * d["accepted"], *d["curate"], sessions=30))
        add("Operate", "Models", "Study: reading, decoding, challenging public sources", study,
            f"{docs_month:,.0f} documents a month, {d['relevant']:.0%} relevant; public data, Flex where possible")
        add("Operate", "Models", "Estate refresh (Surveyor)", self.token_eur("triage", "estate", "Std", estate_calls, *ESTATE_CALL, sessions=60),
            f"{estate_calls:,.0f} calls a month (rules first, model for the rest)")
        add("Operate", "Models", "Sampled scoring of production cases", self.token_eur("judge", "estate", "Std", cases * SAMPLE_SHARE, *JUDGE_CALL),
            f"{SAMPLE_SHARE:.0%} of cases scored by evaluators on another model family")
        emb = P.get("Foundry Models", product="Azure OpenAI", sku="text-embedding-3-large-glbl") * 1000
        add("Operate", "Models", "Embeddings for the Atlas index", EMBED_TOKENS_M * emb, f"{EMBED_TOKENS_M:g} M tokens a month")

        # ---- Operate profile: runtime ------------------------------------------
        hv = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted vCPU Usage")
        hm = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted Memory Usage")
        host_rate = HOSTED_VCPU * hv + HOSTED_GIB * hm
        hosted_h = (cases * CASE_HOSTED_H + WATCH_RUNS * WATCH_RUN_MIN / 60 + docs_month * STUDY_DOC_MIN / 60
                    + estate_calls * ESTATE_CALL_MIN / 60)
        add("Operate", "Runtime", "Hosted agents: active time plus idle timeout", hosted_h * host_rate,
            f"{hosted_h:,.0f} hours at {HOSTED_VCPU:g} vCPU and {HOSTED_GIB:g} GiB; nothing bills between sessions")
        orch = (cases * EXEC_PER_CASE + WATCH_RUNS * 12 + docs_month * 6 + estate_calls * 2) * FN_REPLAY
        tools_exec = cases * TOOL_CALLS_PER_CASE + estate_calls * TOOL_CALLS_PER_ESTATE_CALL
        ready_n = k["always_ready"]
        fb = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Baseline")
        fr = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Execution Time")
        fre = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Total Executions")
        fx = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Execution Time", pick="max")
        fe = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Total Executions", pick="max")
        ready_x = orch * FN_READY_SHARE if ready_n else 0.0
        od_x = orch - ready_x + tools_exec
        od_gb_s = od_x * FN_GB_S_PER_EXEC + s["analysis_gb_s"]
        if ready_n:
            add("Operate", "Runtime", "Azure Functions: one always-ready instance for the Durable group (Learn recommends it)",
                ready_n * FN_INSTANCE_GB * 3600 * HOURS * fb,
                f"{ready_n} instance(s) of {FN_INSTANCE_GB} GB; the baseline bills while idle", idle=1.0)
        fn = (ready_x * FN_GB_S_PER_EXEC * fr + ready_x / 10.0 * fre
              + max(0.0, od_gb_s - FN_FREE_GB_S) * fx + max(0.0, od_x - FN_FREE_EXEC) / 10.0 * fe)
        add("Operate", "Runtime", "Azure Functions on Flex Consumption: workflows, tool services, approvals, bot, action runner, cost analysis", fn,
            f"{orch + tools_exec:,.0f} executions and {od_gb_s + ready_x * FN_GB_S_PER_EXEC:,.0f} GB-seconds a month; on-demand after the free grant; zip deployment, no container registry")
        add("Operate", "Runtime", "Durable Functions state (Azure Storage provider)", MANUAL["durable_storage_env"][0] * (1 + cases / 5000.0),
            "estimate: queue polling and task-hub tables", idle=1.0)

        # ---- Operate profile: knowledge and data -----------------------------------
        units = s["search_units"] + k["extra_search_units"]
        srch = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Basic", meter="Basic Unit")
        add("Operate", "Knowledge", "AI Search Basic (Atlas index)", units * srch * HOURS,
            f"{units} unit(s); runs while idle", idle=1.0)
        sem = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Semantic Ranker", meter="Semantic Ranker queries")
        queries = cases * SEARCH_QUERIES_PER_CASE + docs_month * 3
        add("Operate", "Knowledge", "AI Search semantic ranker", max(0.0, queries - SEARCH_FREE_QUERIES) / 1000.0 * sem,
            f"{queries:,.0f} queries, first {SEARCH_FREE_QUERIES:,} free")
        ru = P.get("Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs", meter="1M RUs")
        st = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="Data Stored")
        ru_m = cases * COSMOS_RU_M_PER_CASE + s["resources"] * COSMOS_RU_M_PER_RESOURCE
        gb = s["ops_gb"] + (BYO_FOUNDRY_GB if k["foundry_byo_data"] else 0)
        add("Operate", "Data", "Cosmos DB serverless (estate model, ledger, approvals)", ru_m * ru + gb * st,
            f"{ru_m:,.1f} M request units and {gb:g} GB; scale to zero", idle=gb * st / max(ru_m * ru + gb * st, 1e-9))
        hot = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Hot ZRS", meter="Hot ZRS Data Stored", pick="max")
        wr = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Hot ZRS", meter="Hot ZRS Write Operations")
        tb = s["lake_gb"] + s["ledger_gb"] + (BYO_FOUNDRY_GB if k["foundry_byo_data"] else 0)
        add("Operate", "Data", "Blob: cost lake and immutable audit log", tb * hot + s["storage_ops_10k"] * wr,
            f"{tb:g} GB Hot ZRS and {s['storage_ops_10k'] * 10:,.0f}k write operations", idle=tb * hot / max(tb * hot + s["storage_ops_10k"] * wr, 1e-9))

        # ---- Operate profile: network, observability, safety, channels --------------
        pe_h = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard", meter="Standard Private Endpoint")
        pe_gb = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard",
                      meter="Standard Data Processed - Egress", pick="max")
        pes = PE_OPERATE + (PE_BYO_FOUNDRY if k["foundry_byo_data"] else 0)
        add("Operate", "Network", "Private endpoints (hourly)", pes * pe_h * HOURS,
            f"{pes} endpoints (Foundry account, Search, Cosmos, audit Storage, platform Storage blob, queue and table, Key Vault); the Evaluate profile has none", idle=1.0)
        add("Operate", "Network", "Private endpoints (data processed)", s["dp_gb"] * pe_gb * 2, f"{s['dp_gb']} GB in and out")
        la_a = P.get("Log Analytics", product="Log Analytics", sku="Analytics Logs", meter="Analytics Logs Data Ingestion", pick="max")
        la_b = P.get("Azure Monitor", product="Azure Monitor", sku="Basic Logs", meter="Basic Logs Data Ingestion")
        la_x = P.get("Azure Monitor", product="Azure Monitor", sku="Auxiliary Logs", meter="Auxiliary Logs Data Ingestion")
        if k["la_split"] == "analytics":
            la = max(0.0, s["la_gb"] - 5) * la_a
            lnote = f"{s['la_gb']} GB, all Analytics, 5 GB free"
        else:
            sp = LA_SPLIT
            la = max(0.0, sp["analytics"] * s["la_gb"] - 5) * la_a + sp["basic"] * s["la_gb"] * la_b + sp["auxiliary"] * s["la_gb"] * la_x
            lnote = f"{s['la_gb']} GB: {sp['analytics']:.0%} Analytics, {sp['basic']:.0%} Basic, {sp['auxiliary']:.0%} Auxiliary plan; 5 GB free"
        add("Operate", "Observability", "Log Analytics ingestion (traces, hub logs, diagnostics)", la, lnote)
        cs = P.get("Foundry Tools", product="Content Safety", sku="Standard", meter="Standard Text Records")
        cs_rec = cases * CS_RECORDS_PER_CASE + docs_month * CS_RECORDS_PER_DOC
        add("Operate", "Safety", "Content Safety on untrusted text (where it enters)", cs_rec / 1000.0 * cs,
            f"{cs_rec:,.0f} text records of 1,000 characters: tool results and owner replies, public documents")
        pii_rec = (cases * 6 + estate_calls * PII_SURVEYOR_SHARE) * PII_RECORDS_PER_CALL
        add("Operate", "Safety", "PII detection on people data", pii_rec / 1000.0 * MANUAL["language_pii_per_1k"][0],
            f"{pii_rec:,.0f} records at the research rate (UNVERIFIED)")
        kv = P.get("Key Vault", product="Key Vault", sku="Standard", meter="Operations")
        add("Operate", "Security", "Key Vault (the few secrets that cannot be keyless)", s["kv_ops_10k"] * kv,
            f"one vault; {s['kv_ops_10k'] * 10:,}k operations")
        if k["defender_ai"]:
            tokens_k = ((case_tokens_in + case_tokens_out) * cases * scale + leads * 3_300 + estate_calls * 5_500) / 1000.0
            add("Operate", "Security", "Defender for AI Services (optional)", tokens_k * MANUAL["defender_ai_per_1k_tokens"][0],
                f"{tokens_k/1e3:,.0f} M tokens scanned; token-metered")
        if k["own_hub"]:
            dev = P.get("API Management", product="API Management", sku="Developer", meter="Developer Unit")
            eh = P.get("Event Hubs", product="Event Hubs", sku="Standard", meter="Standard Throughput Unit")
            c100 = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="100 RU/s")
            add("Operate", "Hub", "Own small hub: API Management Developer, Event Hubs, Cosmos 7 x 400 RU/s, Logic App, 9 private endpoints",
                (dev + eh) * HOURS + 28 * c100 * HOURS + MANUAL["logic_app_ws1"][0] + 9 * pe_h * HOURS + MANUAL["hub_misc"][0],
                "only when the organisation has no hub; otherwise shared and not ours", idle=1.0)

        # ---- Evaluate profile (dev: synthetic data, no private endpoints) -----------
        tier = "Flex"
        n_comp, n_e2e = s["eval_changes"] * COMPONENT_CASES, s["eval_releases"] * E2E_CASES
        comp = self.token_eur("reason", "public", tier, n_comp * COMPONENT_CALLS[0], *COMPONENT_CALLS[1:], sessions=n_comp)
        e2e = sum(self.token_eur(al, "public", tier if al != "judge" else "Std", n_e2e * c * sh, i, pf, o, sessions=n_e2e * sh)
                  for _, c, i, pf, o, al, sh in CASE_MIX)
        judged = self.token_eur("judge", "public", "Std", n_comp + n_e2e, *JUDGE_CALL)
        rt = SAFETY_ATTACKS * s["safety_runs"]
        t, a, e = (SAFETY_ROUND_TRIP[x] for x in ("target", "attacker", "evaluator"))
        safety = (self.token_eur("reason", "public", tier, rt, *t) + self.token_eur("judge", "public", "Std", rt, *a)
                  + self.token_eur("judge", "public", "Std", rt, *e))
        add("Evaluate", "Models", "Evaluation on change: component and end-to-end suites, judged", comp + e2e + judged,
            f"{s['eval_changes']} changes x {COMPONENT_CASES} component cases and {s['eval_releases']} releases x {E2E_CASES} full cases on synthetic estates; Flex")
        add("Evaluate", "Models", "Safety suites and red teaming", safety, f"{s['safety_runs']} run(s) of {SAFETY_ATTACKS:,} attacks a month")
        smoke = self.token_eur("reason", "public", "Std", DEV_SMOKE_CALLS, DEV_SMOKE_TOKENS, 0, 0)
        add("Evaluate", "Models", "Development smoke tests", smoke, f"{DEV_SMOKE_CALLS:,} calls of {DEV_SMOKE_TOKENS:,} tokens")
        eval_h = n_comp * COMPONENT_CASE_H + n_e2e * E2E_CASE_H + rt * 0.0005
        add("Evaluate", "Runtime", "Hosted agents in dev (evaluation runs)", eval_h * host_rate, f"{eval_h:,.0f} hours")
        add("Evaluate", "Data", "Dev platform: Cosmos serverless, Blob, AI Search Free, Functions within free grants",
            1.0 * ru + 1.0 * st + 2.0 * hot, "one small serverless environment, no private endpoints")

        groups: dict[str, float] = {}
        for r in L:
            groups[r["group"]] = groups.get(r["group"], 0.0) + r["eur"]
        total = round(sum(r["eur"] for r in L), 2)
        op = round(sum(r["eur"] for r in L if r["profile"] == "Operate"), 2)
        idle = round(sum(r["idle"] for r in L if r["profile"] == "Operate"), 2)
        review_h = (cases * OWNER_MIN_PER_CASE) / 60.0
        atlas_changes = docs_month * STUDY_DOC["relevant"] * STUDY_DOC["accepted"] / CLAIMS_PER_CHANGE
        return dict(name=name, lines=L, groups={g: round(v, 2) for g, v in groups.items()}, total=total, operate=op,
                    evaluate=round(total - op, 2), idle=idle, per_case=round(total / cases, 2),
                    breakeven_pct=round(100.0 * total / s["spend"], 3), params=s,
                    owner_hours=round(review_h, 1), atlas_changes=round(atlas_changes, 1),
                    reviewer_hours=round(atlas_changes * REVIEW_MIN_PER_ATLAS_CHANGE / 60.0, 1))


def run_all(prices: Prices, **knobs) -> dict[str, dict]:
    m = Model(prices, **knobs)
    return {n: m.scenario(n) for n in SCENARIOS}


def report(prices: Prices) -> str:
    base = run_all(prices)
    names = list(SCENARIOS)
    out: list[str] = []
    out.append(f"*Generated by `tools/cost-model.py` from `docs/design/cost/prices-snapshot.json` (Azure Retail Prices API, EUR, "
               f"{REGION}, 730 hours a month, retrieved {prices.generated[:10]}). Do not edit by hand.*")
    out.append("")
    out.append("**Headline**")
    out.append("")
    for n in names:
        b = base[n]
        out.append(f"- **{n}:** {fmt(b['total'])} EUR a month in total (Operate profile {fmt(b['operate'])}, dev environment "
                   f"{fmt(b['evaluate'])}); the Operate idle floor is {fmt(b['idle'])}; it breaks even by saving {b['breakeven_pct']:.2f} % "
                   f"of the Azure spend it manages.")
    out.append("")
    out.append("**Scenario parameters**")
    out.append("")
    out.append("| Parameter | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    for label, key in [("Subscriptions", "subs"), ("Resources", "resources"), ("Resource owners", "owners"),
                       ("Cases that reach an owner a month", "cases"), ("Azure spend under management (EUR a month)", "spend"),
                       ("Public documents read a day", "study_docs_day"), ("Releases evaluated a month", "eval_releases")]:
        out.append(f"| {label} | " + " | ".join(f"{SCENARIOS[n][key]:,}" for n in names) + " |")
    out.append("")
    out.append("**Monthly cost (EUR), Operate profile plus the dev environment**")
    out.append("")
    out.append("| Line | Profile | " + " | ".join(names) + " |")
    out.append("|---|---|" + "---|" * len(names))
    labels: list[tuple[str, str]] = []
    for r in base[names[0]]["lines"]:
        labels.append((r["label"], r["profile"]))
    for n in names[1:]:
        for r in base[n]["lines"]:
            if (r["label"], r["profile"]) not in labels:
                labels.append((r["label"], r["profile"]))
    for lab, prof in labels:
        cells = []
        for n in names:
            v = next((r["eur"] for r in base[n]["lines"] if r["label"] == lab and r["profile"] == prof), 0.0)
            cells.append(fmt(v))
        out.append(f"| {lab} | {prof} | " + " | ".join(cells) + " |")
    out.append("| **Operate profile** | | " + " | ".join(f"**{fmt(base[n]['operate'])}**" for n in names) + " |")
    out.append("| **Evaluate profile (dev)** | | " + " | ".join(f"**{fmt(base[n]['evaluate'])}**" for n in names) + " |")
    out.append("| **Total** | | " + " | ".join(f"**{fmt(base[n]['total'])}**" for n in names) + " |")
    out.append("")
    out.append("**What the cost means**")
    out.append("")
    out.append("| | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    out.append("| Idle floor of the Operate profile (EUR a month, nobody using it) | " + " | ".join(fmt(base[n]["idle"]) for n in names) + " |")
    out.append("| Total per case that reaches an owner (EUR) | " + " | ".join(fmt(base[n]["per_case"]) for n in names) + " |")
    out.append("| Break-even: share of managed spend it must save to pay for itself | " + " | ".join(f"{base[n]['breakeven_pct']:.2f} %" for n in names) + " |")
    out.append("| Owner time on cases (hours a month, 5 minutes a case) | " + " | ".join(f"{base[n]['owner_hours']:,.0f}" for n in names) + " |")
    out.append("| Atlas pull requests to review a month (10 minutes each: hours) | " + " | ".join(
        f"{base[n]['atlas_changes']:,.0f} ({base[n]['reviewer_hours']:,.1f} h)" for n in names) + " |")
    out.append("")
    out.append("**Sensitivities: change in the total (EUR a month)**")
    out.append("")
    out.append("| What changes | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    for label, knobs in SENSITIVITIES:
        alt = run_all(prices, **knobs)
        out.append(f"| {label} | " + " | ".join(f"{alt[n]['total'] - base[n]['total']:+,.0f}" for n in names) + " |")
    out.append("")
    out.append("**Meters used** (EUR, Sweden Central unless marked Global)")
    out.append("")
    out.append("| Meter | EUR | Unit |")
    out.append("|---|---|---|")
    for sel, (v, unit) in sorted(prices.used.items()):
        parts = sel.split("|")
        label = " / ".join(x for x in (parts[0], parts[2], parts[3], parts[4]) if x and x != "None")
        out.append(f"| {label}{' (Global)' if parts[1] == 'Global' else ''} | {v:.6g} | {unit} |")
    out.append("")
    out.append("**Quoted, not in the price API:** " + "; ".join(f"{k.replace('_', ' ')}: {v[0]:g} ({v[1]})" for k, v in MANUAL.items()) + ".")
    return "\n".join(out)


def block(prices: Prices) -> str:
    return f"{BEGIN}\n{report(prices)}\n{END}"


def split_doc(text: str) -> tuple[str, str, str]:
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0 or j < i:
        raise ValueError(f"the document needs one {BEGIN} ... {END} pair")
    return text[:i], text[i:j + len(END)], text[j + len(END):]


def check_doc(text: str, prices: Prices) -> list[str]:
    try:
        _, cur, _ = split_doc(text)
    except ValueError as e:
        return [str(e)]
    return [] if cur == block(prices) else ["the generated cost block is stale: run `python tools/cost-model.py --update-doc <file>`"]


def self_test() -> int:
    p = Prices(SNAP)
    for bad in (dict(service="Foundry Models", product="No Such Product", sku="x"),
                dict(service="Foundry Models", product="Azure OpenAI GPT6", sku=r"6\.1-sol ShortCo Inp .*")):
        try:
            p.get(**bad)
        except LookupError:
            continue
        raise AssertionError(f"selector should have failed: {bad}")
    try:
        Model(p, no_such_knob=1)
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown knob must fail")
    base = run_all(p)
    tot = [base[n]["total"] for n in SCENARIOS]
    assert tot == sorted(tot) and len(set(tot)) == 3, "scenario totals must grow with scale"
    for n, r in base.items():
        assert all(x["eur"] >= 0 and 0 <= x["idle"] <= x["eur"] + 0.01 for x in r["lines"]), f"negative or impossible line in {n}"
        assert r["idle"] <= r["operate"] and abs(r["operate"] + r["evaluate"] - r["total"]) < 0.02
    more = {"token_scale": 2.0, "cache": False, "flex": False, "la_split": "analytics", "own_hub": True, "defender_ai": True,
            "extra_search_units": 1}
    for knob, val in more.items():
        alt = run_all(p, **{knob: val})
        assert alt["Team"]["total"] > base["Team"]["total"], f"{knob}={val} must cost more"
    assert run_all(p, estate_zone="Gl")["Team"]["total"] < base["Team"]["total"], "Global Standard must be cheaper than Data Zone"
    assert run_all(p, foundry_byo_data=True)["Team"]["total"] > base["Team"]["total"], "bring-your-own agent data must cost more"
    doc = f"intro\n{block(p)}\noutro\n"
    assert check_doc(doc, p) == []
    assert check_doc(doc.replace("Pilot", "Pilot2", 1), p), "a changed block must be reported as stale"
    assert check_doc("no markers", p), "a missing block must be reported"
    print("self-test OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lines", metavar="SCENARIO")
    ap.add_argument("--update-doc", metavar="FILE")
    ap.add_argument("--check", metavar="FILE")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    prices = Prices(SNAP)
    if a.json:
        print(json.dumps(run_all(prices), indent=1))
    elif a.lines:
        for r in run_all(prices)[a.lines]["lines"]:
            print(f"{r['profile']:9s} {r['group']:13s} {r['eur']:>10,.2f} idle {r['idle']:>9,.2f}  {r['label']}  -- {r['note']}")
    elif a.update_doc:
        path = Path(a.update_doc)
        head, _, tail = split_doc(path.read_text(encoding="utf-8"))
        path.write_text(head + block(prices) + tail, encoding="utf-8", newline="\n")
        print(f"updated {a.update_doc}")
    elif a.check:
        problems = check_doc(Path(a.check).read_text(encoding="utf-8"), prices)
        for x in problems:
            print(f"{a.check}: {x}")
        return 1 if problems else 0
    else:
        print(report(prices))
    return 0


if __name__ == "__main__":
    sys.exit(main())
