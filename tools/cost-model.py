#!/usr/bin/env python3
"""Monthly cost model for Azure Cost in Action (standard library only).

Reads docs/design/cost/prices-snapshot.json (written by tools/fetch-prices.py from the
Azure Retail Prices API) and prices three scale scenarios.  Every meter is resolved by an
exact selector: a selector that matches zero meters, or more than one, stops the run, so a
changed price list can never silently change a number.

    python tools/cost-model.py                      # markdown report to stdout
    python tools/cost-model.py --json               # machine-readable
    python tools/cost-model.py --lines Team         # every line item of one scenario
    python tools/cost-model.py --quotas Team        # hub contract quotas derived from the plan
    python tools/cost-model.py --update-doc docs/design/12-cost-and-finops.md
    python tools/cost-model.py --check  docs/design/12-cost-and-finops.md   # stale block, or a quota that diverges from the plan

All quantities below are *seeds*: assumptions to be replaced by measurements (spike S-COST-1).
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
BEGIN, END = "<!-- cost-model:begin -->", "<!-- cost-model:end -->"
REGION = "swedencentral"

# ---------------------------------------------------------------------------
# Scenarios (seeds).  Case-driven work scales with `cases`; clocks with `subs`.
# `accounts` = private Foundry accounts, each with its own standard-setup trio (AI Search, Cosmos DB,
# Storage): Pilot = production + development, Team adds test, Enterprise adds the Lab.  Accounts are
# created in the phase that needs them (design 14), so a smaller scenario never pays for a larger one.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "Pilot": dict(subs=5, resources=500, owners=5, cases=100, spend=20_000,
                  survey_calls=150, study_changes=40, exam_cases=600, accounts=2,
                  pe=28, la_gb=8, lake_gb=20, ledger_gb=1, ops_ru_m=20, ops_gb=2, search_units=2,
                  aca_vcpu_h=150, aca_req_m=1, dp_gb=50, own_subs=4, peer_gb=10,
                  rt_scans=6, rt_attacks=500, fn_always_ready=1, fw_gb=100),
    "Team": dict(subs=50, resources=10_000, owners=100, cases=1_000, spend=400_000,
                 survey_calls=1_500, study_changes=40, exam_cases=1_350, accounts=3,
                 pe=34, la_gb=40, lake_gb=300, ledger_gb=5, ops_ru_m=200, ops_gb=10, search_units=3,
                 aca_vcpu_h=600, aca_req_m=10, dp_gb=500, own_subs=5, peer_gb=50,
                 rt_scans=8, rt_attacks=1_000, fn_always_ready=1, fw_gb=500),
    "Enterprise": dict(subs=1000, resources=200_000, owners=2000, cases=20_000, spend=8_000_000,
                       survey_calls=30_000, study_changes=40, exam_cases=2_700, accounts=4,
                       pe=40, la_gb=400, lake_gb=4_000, ledger_gb=40, ops_ru_m=1_500, ops_gb=100, search_units=5,
                       aca_vcpu_h=3_000, aca_req_m=100, dp_gb=5_000, own_subs=8, peer_gb=500,
                       rt_scans=12, rt_attacks=2_000, fn_always_ready=2, fw_gb=5_000),
}

# Token workloads per *case* (W4): role, alias, contract group, then calls per case, input tokens per call,
# cached share of input, cache-write tokens (charged once per session: one session per role per case) and
# output tokens per call.
CASE_WORK = [
    ("Detective", "reason", "investigate", dict(calls=10, tin=15_000, cached=0.70, cw=6_000, tout=1_500)),
    ("Skeptic", "judge", "investigate", dict(calls=4, tin=12_000, cached=0.00, cw=0, tout=1_000)),
    ("Economist", "reason", "investigate", dict(calls=4, tin=10_000, cached=0.60, cw=5_000, tout=1_000)),
    ("Diplomat", "reason", "converse", dict(calls=2, tin=6_000, cached=0.50, cw=3_000, tout=800)),
    ("Triage", "luna", "conduct", dict(calls=6, tin=3_000, cached=0.50, cw=1_500, tout=300)),
]
# Hosted-agent sessions per case: role, active minutes, idle-timeout minutes.  Whether idle time is billed is
# UNVERIFIED (the hosted-agents page shows active and idle states and states no idle price), so it is billed here.
HOSTED_SESSIONS = [("Detective", 12, 5), ("Skeptic", 6, 5), ("Economist", 5, 5), ("Diplomat", 2, 15), ("Triage", 3, 2)]
HOSTED_H_PER_CASE = sum(a + i for _, a, i in HOSTED_SESSIONS) / 60.0
SANDBOX_H_PER_CASE = 1.0      # one batched session-hour per case (typed query tools are preferred, 05 section 5; UNVERIFIED hour rounding)
RT_PER_ATTACK = dict(target=dict(tin=3_000, tout=600), attacker=dict(tin=1_500, tout=400), evaluator=dict(tin=3_000, tout=200))
FN_EXEC_PER_CASE = 150        # Durable Functions activity executions per case or exam case (leaf calls, record writes, timers)
FN_GB_S_PER_EXEC = 2.0        # a 2 GB instance for about a second
PII_RECORDS_PER_CALL = 10     # 1,000-character records of free text pseudonymised in the tool services per Surveyor or Diplomat call
QUOTA_HEADROOM = 1.5          # monthly contract quota = planned tokens x this; the hub cap is therefore 1.5 x the plan
QUOTA_CAP_LIMIT = 2.0         # --check fails if the summed euro cap exceeds this multiple of the token plan
LABOUR_RATE_EUR = 75.0        # stated seed for the labour sensitivity, EUR per hour
LABOUR_HOURS = (20, 40, 80, 160)
KEY_VAULTS = 9                # secrets, the hub's, the registry's, plus one vault each for the Approval service, Policy service, broker, runner, Verifier and Audit Writer signing keys (07 section 6.1)
ATLAS_QUERIES_PER_CASE = 20   # Atlas retrievals per case (Detective, Economist, Diplomat), each through the semantic ranker

# Labels of the token lines (the report groups the workloads by these).
L_CASES = "Cases (W4) on the EU Data Zone"
L_WATCH = "Watch (W1): triage of the release feed"
L_STUDY = "Study (W2): Scholar, Cartographer, Librarian"
L_SURVEY = "Survey (W3): Surveyor on changes"
L_DREAM = "Dream (W7): nightly consolidation"
L_EXAM = "Exams and release gates (W8) on synthetic estates"
L_RT = "Red teaming (L5): attacker, target and evaluator (UNVERIFIED seed)"
L_EMB = "Embeddings (Atlas releases and retrieval)"

# Manual figures that are not in the price API.  Each names its source.
MANUAL = {
    "language_pii_per_1k": (0.88, "research/citadel.md section 7 (Azure Language PII, EUR per 1,000 records, falling to 0.22 at volume; the vendor page rendered no amount, UNVERIFIED)"),
    "spine_task_hub_storage": (4.0, "estimate: about 1.3 M queue-polling transactions a month at 10 s plus tables and blobs (Learn: Flex Consumption guidance); no queue or table meters in the snapshot"),
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
    def tokens_cost(price: dict, calls: float, tin: float, cached: float, cw: float, tout: float,
                    sessions: float = 1.0, cw_per_call: bool = False) -> float:
        """Cache writes are charged once per session (design 05 section 7); `cw_per_call` is the pessimistic reading."""
        per_call = (tin * (1 - cached) * price["inp"] + tin * cached * price["cd"] + tout * price["out"]) / 1e6
        writes = cw * price["cw"] / 1e6 * (calls if cw_per_call else sessions)
        return calls * per_call + writes

    def cost_of(self, x: dict) -> float:
        return self.tokens_cost(x["price"], x["calls"], x["tin"], x["cached"], x["cw"], x["tout"], x["sessions"])

    def case_cost(self, zone: str = "DZ", svc_class: str = "Std", detail: bool = False, cw_per_call: bool = False):
        total, rows = 0.0, []
        for role, alias, _group, w in CASE_WORK:
            c = self.tokens_cost(self.alias(alias, zone, svc_class), **w, cw_per_call=cw_per_call)
            total += c
            rows.append((role, alias, c))
        return (total, rows) if detail else total

    def workloads(self, s: dict) -> list[dict]:
        """Every token workload of a scenario with its contract group and environment.  The euro lines and the
        hub quotas both derive from this list, so a quota can never drift from the plan it caps."""
        W: list[dict] = []

        def add(label, group, env, price, calls, tin, cached, cw, tout, sessions):
            W.append(dict(label=label, group=group, env=env, price=price, calls=calls, tin=tin, cached=cached,
                          cw=cw, tout=tout, sessions=sessions))

        cases, ch, calls = s["cases"], s["study_changes"], s["survey_calls"]
        sol_eu, luna_eu = self.gpt6("6.1-sol", "DZ"), self.gpt6("6-luna", "DZ")
        sol_gl, luna_gl = self.gpt6("6.1-sol", "Gl"), self.gpt6("6-luna", "Gl")
        for role, alias, group, w in CASE_WORK:
            add(L_CASES, group, "prod", self.alias(alias, "DZ"), cases * w["calls"], w["tin"], w["cached"], w["cw"], w["tout"], cases)
        feed_items = 150 * 30
        add(L_WATCH, "study", "prod", luna_gl, feed_items, 1_500, 0.5, 0, 100, feed_items)
        add(L_STUDY, "study", "prod", sol_gl, ch * 12, 20_000, 0.5, 6_000, 2_000, ch)
        add(L_STUDY, "study", "prod", sol_gl, ch * 4, 15_000, 0.5, 4_000, 1_500, ch)
        add(L_STUDY, "curate", "prod", sol_gl, ch * 4, 15_000, 0.5, 4_000, 1_500, ch)
        add(L_SURVEY, "survey", "prod", luna_eu, 0.8 * calls, 8_000, 0.5, 2_000, 600, 0.8 * calls)
        add(L_SURVEY, "survey", "prod", sol_eu, 0.2 * calls, 8_000, 0.5, 2_000, 600, 0.2 * calls)
        add(L_DREAM, "govern", "prod", sol_eu, 30 * (5 + cases / 200.0), 20_000, 0.5, 5_000, 2_000, 30)
        ex = [dict(label=L_EXAM, group=group, env="exam", price=self.alias(alias, "Gl", "Flex"), calls=s["exam_cases"] * w["calls"],
                   tin=w["tin"], cached=w["cached"], cw=w["cw"], tout=w["tout"], sessions=s["exam_cases"])
              for role, alias, group, w in CASE_WORK]
        W.extend(ex)
        W.extend(dict(x, group="examine", calls=0.3 * x["calls"], sessions=0.3 * x["sessions"]) for x in ex)   # judges: 30 % more
        n_attacks = s["rt_scans"] * s["rt_attacks"]
        rt = RT_PER_ATTACK
        add(L_RT, "investigate", "exam", self.alias("reason", "Gl", "Flex"), n_attacks, rt["target"]["tin"], 0, 0, rt["target"]["tout"], 0)
        add(L_RT, "examine", "exam", self.alias("luna", "Gl", "Flex"), n_attacks, rt["attacker"]["tin"], 0, 0, rt["attacker"]["tout"], 0)
        add(L_RT, "examine", "exam", self.alias("luna", "Gl", "Flex"), n_attacks, rt["evaluator"]["tin"], 0, 0, rt["evaluator"]["tout"], 0)
        embed = self.p.get("Foundry Models", product="Azure OpenAI", sku="text-embedding-3-large-regional") * 1000.0
        add(L_EMB, "curate", "prod", dict(inp=embed, out=0.0, cd=embed, cw=0.0), 1, 5_000_000 * 4 + cases * 50 * 300, 0, 0, 0, 1)
        return W

    def quotas(self, s: dict, wl: list[dict] | None = None) -> list[dict]:
        """Monthly token quota and implied euro cap per (group, environment): the plan x QUOTA_HEADROOM."""
        agg: dict[tuple[str, str], list[float]] = {}
        for x in (wl or self.workloads(s)):
            a = agg.setdefault((x["group"], x["env"]), [0.0, 0.0])
            a[0] += x["calls"] * (x["tin"] + x["tout"])
            a[1] += self.cost_of(x)
        rows = []
        for (g, e), (tok, eur) in sorted(agg.items(), key=lambda kv: (kv[0][1] != "prod", kv[0][0])):
            q = math.ceil(tok * QUOTA_HEADROOM / 1e6) * 1e6
            rows.append(dict(group=g, env=e, planned_tokens=tok, quota_tokens=q, planned_eur=eur, cap_eur=eur * q / tok))
        return rows

    # -- one scenario ------------------------------------------------------
    def scenario(self, name: str, hub: str = "shared") -> dict:
        s = SCENARIOS[name]
        P, L = self.p, []

        def add(group: str, label: str, eur: float, note: str = "") -> None:
            L.append(dict(group=group, label=label, eur=round(eur, 2), note=note))

        # tokens -----------------------------------------------------------
        calls = s["survey_calls"]
        feed_items = 150 * 30
        case_eu = self.case_cost("DZ", "Std")
        wl = self.workloads(s)
        notes = {
            L_CASES: f"{s['cases']} cases at EUR {case_eu:.3f} of marginal tokens each",
            L_WATCH: "public data, Global",
            L_STUDY: "public data, Global Standard",
            L_SURVEY: "80% Luna, 20% Sol, EU Data Zone",
            L_DREAM: "estate lessons, EU Data Zone (flex is Global only)",
            L_EXAM: "Flex, Global, plus 30% for judges",
            L_RT: f"{s['rt_scans']} scans of {s['rt_attacks']:,} attacks on Flex, Global; the self-hosted harness pays the same tokens",
            L_EMB: "weekly index rebuild plus retrieval",
        }
        order: list[str] = []
        for x in wl:
            if x["label"] not in order:
                order.append(x["label"])
        for lab in order:
            add("Tokens", lab, sum(self.cost_of(x) for x in wl if x["label"] == lab), notes[lab])
        cs = P.get("Foundry Tools", product="Content Safety", sku="Standard", meter="Standard Text Records")
        records = s["cases"] * 40 + feed_items + calls
        add("Tokens", "Content safety screening of untrusted text", max(0.0, records - 5_000) / 1000.0 * cs,
            f"{records:,.0f} records, 5,000 free")
        pii = (calls + 2 * s["cases"]) * PII_RECORDS_PER_CALL
        add("Tokens", "Personal-data pseudonymisation (Language PII) in the tool services", pii / 1000.0 * MANUAL["language_pii_per_1k"][0],
            f"{pii:,.0f} records at the research rate, UNVERIFIED")

        # compute ------------------------------------------------------------
        hv = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted vCPU Usage")
        hm = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted Memory Usage")
        hosted_h = (s["cases"] + s["exam_cases"]) * HOSTED_H_PER_CASE + s["study_changes"] * 1.0 + calls * 5 / 60.0 + 30 * 0.5
        add("Compute", "Hosted agents: sessions, active plus idle timeout", hosted_h * (hv * 1.0 + hm * 2.0),
            f"{hosted_h:,.0f} h at 1 vCPU and 2 GiB; {HOSTED_H_PER_CASE:.1f} h per case; idle billing UNVERIFIED, billed here")
        sbx = P.get("Azure Container Apps", product="Azure Container Apps", sku="Dynamic Sessions", meter="Dynamic Sessions")
        sbx_h = (s["cases"] + s["exam_cases"]) * SANDBOX_H_PER_CASE
        add("Compute", "Sandbox sessions for model-written analysis, batched", sbx_h * sbx,
            f"{sbx_h:,.0f} session-hours at the dynamic-sessions rate; hour rounding UNVERIFIED")
        fb = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Baseline")
        fx = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Execution Time", pick="max")
        fe = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Total Executions", pick="max")
        execs = (s["cases"] + s["exam_cases"]) * FN_EXEC_PER_CASE + s["subs"] * 30 * 4
        gbs = execs * FN_GB_S_PER_EXEC
        add("Compute", "Durable Functions spine (Flex Consumption): always-ready instance, executions",
            s["fn_always_ready"] * 2 * 3600 * HOURS * fb + max(0.0, gbs - 100_000) * fx + max(0.0, execs - 250_000) / 10.0 * fe,
            f"{s['fn_always_ready']} always-ready 2 GB instance(s) for the durable group, {execs:,.0f} executions, after the free grant")
        add("Compute", "Durable Functions task-hub storage (queue polling at 10 s or less)",
            MANUAL["spine_task_hub_storage"][0] * (1 + s["cases"] / 5000.0), "estimate; queue and table meters are not in the snapshot")
        vcpu_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard vCPU Active Usage")
        mem_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Memory Active Usage")
        req = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Requests")
        grant_v, grant_m, grant_r = 180_000 * s["own_subs"] / 4, 360_000 * s["own_subs"] / 4, 2.0 * s["own_subs"] / 4
        vcpu_sec, gib_sec = s["aca_vcpu_h"] * 3600, s["aca_vcpu_h"] * 3600 * 2
        add("Compute", "Container Apps: tool services, execution plane, adapters",
            max(0, vcpu_sec - grant_v) * vcpu_s + max(0, gib_sec - grant_m) * mem_s + max(0, s["aca_req_m"] - grant_r) * req,
            f"{s['aca_vcpu_h']} vCPU-hours, 2 GiB each, after the free grants")

        # data and observability ----------------------------------------------
        srch = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Basic", meter="Basic Unit")
        add("Data", "AI Search Basic: one per private Foundry account (standard setup); the Atlas index shares production's",
            s["search_units"] * srch * HOURS, f"{s['accounts']} accounts, {s['search_units']} unit(s)")
        sem = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Semantic Ranker", meter="Semantic Ranker queries")
        atlas_q = s["cases"] * ATLAS_QUERIES_PER_CASE + s["study_changes"] * 100 + calls * 2
        add("Data", "AI Search semantic ranker on Atlas queries (1,000 free a month)", max(0.0, atlas_q - 1000) / 1000.0 * sem,
            f"{atlas_q:,.0f} queries; switched off where the exam shows no gain (lever 13)")
        ru = P.get("Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs", meter="1M RUs")
        st = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="Data Stored")
        acc = s["accounts"]
        add("Data", "Cosmos DB serverless: operational store and one account per Foundry account", (s["ops_ru_m"] + 20 * acc) * ru + (s["ops_gb"] + 5 * acc) * st,
            f"{s['ops_ru_m']} M request units and {s['ops_gb']} GB, plus 20 M and 5 GB for each of {acc} Foundry accounts")
        cool = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Cool ZRS", meter="Cool ZRS Data Stored", pick="max")
        hot = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Hot ZRS", meter="Hot ZRS Data Stored", pick="max")
        add("Data", "Cost lake (Cool ZRS) and ledger (Hot ZRS)", s["lake_gb"] * cool + s["ledger_gb"] * hot * 2, f"{s['lake_gb']} GB lake, {s['ledger_gb']} GB ledger x2 for redundancy")
        rec_gb = (35 * s["ops_gb"] + s["ledger_gb"]) * 2
        add("Data", "Recovery lake: hourly exports and daily snapshots in two EU regions (35-day retention)", rec_gb * cool,
            f"{rec_gb:,.0f} GB over both copies at the Cool ZRS price; the copy traffic between regions is cents")
        acr_day = P.get("Container Registry", product="Container Registry", sku="Premium", meter="Premium Registry Unit")
        add("Data", "Container Registry Premium (private pull)", acr_day * DAYS, "one registry")
        pe_h = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard", meter="Standard Private Endpoint")
        pe_gb = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard",
                      meter="Standard Data Processed - Egress", pick="max")
        add("Network", "Private endpoints (hourly)", s["pe"] * pe_h * HOURS, f"{s['pe']} endpoints (4 per private Foundry account, one per signing vault, the spine's storage, the recovery lake, ours)")
        add("Network", "Private endpoint data processed", s["dp_gb"] * pe_gb * 2, f"{s['dp_gb']} GB in and out")
        peer = P.get("Virtual Network", region="Global", product="Global Virtual Network Peering", sku="Inter-Region", meter="Inter-Region Egress")
        add("Network", "Peering to a hub in another region (both directions)", s["peer_gb"] * peer * 2,
            f"{s['peer_gb']} GB a month of model, tool and trace traffic; zero if the hub is in Sweden Central")
        la_a = P.get("Log Analytics", product="Log Analytics", sku="Analytics Logs", meter="Analytics Logs Data Ingestion", pick="max")
        la_b = P.get("Azure Monitor", product="Azure Monitor", sku="Basic Logs", meter="Basic Logs Data Ingestion")
        la_x = P.get("Azure Monitor", product="Azure Monitor", sku="Auxiliary Logs", meter="Auxiliary Logs Data Ingestion")
        gb = s["la_gb"]
        add("Observability", "Log Analytics ingestion (30% analytics, 50% basic, 20% auxiliary)",
            max(0.0, 0.3 * gb - 5) * la_a + 0.5 * gb * la_b + 0.2 * gb * la_x, f"{gb} GB, 5 GB free")
        drm = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Resource Manager", sku="Per node Std", meter="Per node Std Node")
        dkv = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Key Vault", sku="Per node Std", meter="Per node Std Node")
        add("Security", "Defender for Resource Manager and Key Vault (default tier)", s["own_subs"] * drm * HOURS + KEY_VAULTS * dkv * HOURS,
            f"{s['own_subs']} subscriptions, {KEY_VAULTS} vaults (the approval-signing key has a vault of its own)")

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
        q = self.quotas(s, wl)
        return dict(name=name, hub=hub, lines=L, groups={k: round(v, 2) for k, v in groups.items()}, total=round(total, 2),
                    per_case=round(total / s["cases"], 2), per_sub=round(total / s["subs"], 2),
                    breakeven_pct=round(100.0 * total / s["spend"], 2), params=s, quotas=q,
                    plan_eur=round(sum(r["planned_eur"] for r in q), 2), cap_eur=round(sum(r["cap_eur"] for r in q), 2))

    def optional(self) -> list[tuple[str, float, str]]:
        au = self.p.get("Foundry Tools", product="Azure Agent Unit", sku="SRE", meter="SRE Agent Unit")
        fw_dep = self.p.get("Azure Firewall", product="Azure Firewall", sku="Standard", meter="Standard Deployment")
        fw_gb = self.p.get("Azure Firewall", product="Azure Firewall", sku="Standard", meter="Standard Data Processed")
        dts = self.p.get("Durable Task Scheduler", product="Durable Task Scheduler", sku="Dedicated", meter="Dedicated Capacity Unit")
        return [
            ("Azure SRE Agent, always on (4 units an hour)", 4 * HOURS * au, "price API"),
            ("Agent 365 for 5 sponsors (list)", 5 * MANUAL["agent365_user_usd"][0] * self.p.fx, MANUAL["agent365_user_usd"][1]),
            ("Defender for AI Services at 100 M tokens", 100_000 * MANUAL["defender_ai_per_1k_tokens"][0], MANUAL["defender_ai_per_1k_tokens"][1]),
            ("Front Door Premium, base only", MANUAL["front_door_premium"][0], MANUAL["front_door_premium"][1]),
            ("Confidential Ledger, smallest standard instance", MANUAL["confidential_ledger"][0], MANUAL["confidential_ledger"][1]),
            ("Azure Data Explorer Dev/Test, if kept on", MANUAL["adx_devtest"][0], MANUAL["adx_devtest"][1]),
            ("Azure Firewall Standard, if the landing zone has none (deployment plus 100 GB)", fw_dep * HOURS + 100 * fw_gb, "price API"),
            ("Durable Task Scheduler Dedicated, one capacity unit, only if the storage provider proves too slow", dts * HOURS, "price API"),
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
            for role, alias, _group, w in CASE_WORK:
                pr = price if alias == "reason" else self.alias(alias, zone)
                tot += self.tokens_cost(pr, **w)
            return tot
        nocache = 0.0
        for role, alias, _group, w in CASE_WORK:
            nocache += self.tokens_cost(self.alias(alias, "DZ"), **dict(w, cached=0.0, cw=0))
        return [("Baseline: one case on the EU Data Zone, cache written once per session", base),
                ("Cache written on every call (the pessimistic reading)", self.case_cost("DZ", "Std", cw_per_call=True)),
                ("The same case on Global (not allowed for estate data: the price of residency)", gl),
                ("Investigation tier on Terra instead of Sol", terra("DZ")),
                ("No prompt caching", nocache)]


def fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"


def quota_table(d: dict) -> list[str]:
    out = ["| Group | Environment | Planned tokens a month | Quota (plan x 1.5) | Planned € | Euro cap at the group's own price |",
           "|---|---|---|---|---|---|"]
    for r in d["quotas"]:
        out.append(f"| `{r['group']}` | {r['env']} | {r['planned_tokens'] / 1e6:,.1f} M | {r['quota_tokens'] / 1e6:,.0f} M | "
                   f"€{fmt(r['planned_eur'])} | €{fmt(r['cap_eur'])} |")
    out.append(f"| **Total** | | {sum(r['planned_tokens'] for r in d['quotas']) / 1e6:,.1f} M | "
               f"{sum(r['quota_tokens'] for r in d['quotas']) / 1e6:,.0f} M | **€{fmt(d['plan_eur'])}** | **€{fmt(d['cap_eur'])}** |")
    return out


def validate(model: Model) -> list[str]:
    """A quota that blocks planned work, or a summed cap far above the plan, is a defect (design 04 section 4.3)."""
    errs = []
    for n in SCENARIOS:
        d = model.scenario(n)
        for r in d["quotas"]:
            if r["quota_tokens"] < 1.2 * r["planned_tokens"]:
                errs.append(f"{n}: the quota of {r['group']}/{r['env']} would block planned work")
        if d["cap_eur"] > QUOTA_CAP_LIMIT * d["plan_eur"]:
            errs.append(f"{n}: the summed euro cap {d['cap_eur']:.0f} exceeds {QUOTA_CAP_LIMIT} x the plan {d['plan_eur']:.0f}")
    return errs


def report(model: Model) -> str:
    out = ["| Scenario | Fixed and platform | Compute | Tokens | **Total, shared hub** | Own hub, small | Own hub, medium | Cloud per case, all lines | Per subscription | Break-even, cloud only |",
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
    out.append("Monthly euros, list prices. *Fixed and platform* is data, network, observability and security; *shared hub* means the Citadel hub belongs to the landing zone. "
               "*Cloud per case* divides **every** cloud line by the cases (it is not the marginal token cost, which is in the table below). "
               "Break-even is the share of monitored cloud spend the system must verifiably save to cover its own **cloud** cost "
               "(monitored spend, a seed: " + ", ".join(f"{k} €{v['spend']:,}" for k, v in SCENARIOS.items()) + " a month). "
               "Private Foundry accounts, each with its own AI Search, Cosmos DB and Storage: " +
               ", ".join(f"{k} {v['accounts']}" for k, v in SCENARIOS.items()) + " (production and development; test; the Lab), created in the phase that needs them.")
    out.append("")
    shares = []
    for d in detail:
        g, t = d["groups"], d["total"]
        fixed = sum(v for k, v in g.items() if k not in ("Tokens", "Compute"))
        shares.append(f"{d['name']}: tokens {100 * g['Tokens'] / t:.0f} %, compute {100 * g['Compute'] / t:.0f} %, fixed and platform {100 * fixed / t:.0f} %")
    out.append("**Shares of the total (shared hub):** " + "; ".join(shares) + ".")
    out.append("")
    out.append("**Hub caps next to the plan** (token quotas at " + f"{QUOTA_HEADROOM} x the planned tokens, priced at each group's own price. The hub's token limit is the control, with a small residual overshoot under concurrency (section 6); the plan is the forecast): "
               + "; ".join(f"{d['name']} cap €{fmt(d['cap_eur'])} against a token plan of €{fmt(d['plan_eur'])}" for d in detail) + ".")
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
    out.append("**One case, on the strongest tier, by role** (EU Data Zone, marginal tokens only):")
    out.append("")
    tot, rows = model.case_cost("DZ", "Std", detail=True)
    out.append("| Role | Alias | € per case |")
    out.append("|---|---|---|")
    for role, alias, c in rows:
        out.append(f"| {role} | `acia-{ {'reason':'reason','luna':'triage','judge':'judge-eu'}[alias] }` | {c:.3f} |")
    out.append(f"| **Total** | | **{tot:.3f}** |")
    out.append("")
    out.append("**Sensitivity** (one case, marginal tokens):")
    out.append("")
    out.append("| Variant | € per case |")
    out.append("|---|---|")
    for lab, v in model.sensitivity():
        out.append(f"| {lab} | {v:.3f} |")
    out.append("")
    out.append(f"**With labour: the all-in break-even** (share of monitored spend; labour at €{LABOUR_RATE_EUR:.0f} an hour is a stated seed, not a measurement):")
    out.append("")
    out.append("| Labour a month | " + " | ".join(SCENARIOS) + " |")
    out.append("|---|" + "---|" * len(SCENARIOS))
    out.append("| none (cloud only) | " + " | ".join(f"{d['breakeven_pct']:.2f} %" for d in detail) + " |")
    for h in LABOUR_HOURS:
        out.append(f"| {h} h (€{h * LABOUR_RATE_EUR:,.0f}) | "
                   + " | ".join(f"{100.0 * (d['total'] + h * LABOUR_RATE_EUR) / d['params']['spend']:.2f} %" for d in detail) + " |")
    out.append("")
    team = next(d for d in detail if d["name"] == "Team")
    out.append("**Contract quotas at Team scale.** Every group's monthly token quota is its planned tokens times "
               f"{QUOTA_HEADROOM}, rounded up to a whole million, so a quota can neither block planned work nor float far above it; "
               "`python tools/cost-model.py --quotas Pilot` (or `Enterprise`) prints the others. The euro cap is the quota priced at the group's own blended price:")
    out.append("")
    out.extend(quota_table(team))
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
    ap.add_argument("--quotas", metavar="SCENARIO")
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
    if args.quotas:
        print("\n".join(quota_table(model.scenario(args.quotas, args.hub))))
        return 0
    if args.json:
        print(json.dumps({n: model.scenario(n, args.hub) for n in SCENARIOS}, indent=2, default=str))
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
            errs = validate(model)
            for e in errs:
                print(f"{path}: {e}", file=sys.stderr)
            if m.group(0) != block:
                print(f"{path}: generated block is stale; run tools/cost-model.py --update-doc {path}", file=sys.stderr)
                return 1
            if errs:
                return 1
            print(f"{path}: cost block is current; quotas consistent with the plan")
            return 0
        path.write_text(text[: m.start()] + block + text[m.end():], encoding="utf-8")
        print(f"updated {path}")
        return 0
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
