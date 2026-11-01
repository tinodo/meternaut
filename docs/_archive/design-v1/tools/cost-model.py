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
    python tools/cost-model.py --check  docs/design/12-cost-and-finops.md   # stale block; a quota that diverges from the plan; a contract of design 04 section 4.3 the model does not price
    python tools/cost-model.py --self-test                                  # negative fixtures: each defect above must be caught

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
# `accounts` = private Foundry accounts, one per environment (design 04 section 7), each with its own
# standard-setup trio (AI Search, Cosmos DB, Storage): Pilot = development and production, Team adds test and
# the Lab, Enterprise is the same four at ten to twenty times the volume.  Accounts are created in the phase
# that needs them (design 14), so a smaller scenario never pays for a larger one.
# `envs` = environments with a spine and stores (dev, test, prod); `chain_envs` = those that also run the
# execution chain (the Approval service, the broker, the runner and their signing vaults): Pilot is read-only
# plus shadow, so only production holds the chain and development rehearses with a dry-run runner.
# `gate_*` = the gate plan of design 10 section 4 for one gated domain-release: decoys (G3), comparison
# cases (G4) and the repeats `r` of a case; `gate_releases` = gated domain-releases a month.  Pilot gates one
# narrow domain in shadow (the claim narrows instead of the statistics thinning, design 10).
# ---------------------------------------------------------------------------
SCENARIOS = {
    "Pilot": dict(subs=5, resources=500, owners=5, cases=100, spend=20_000,
                  survey_calls=150, study_changes=40, exam_cases=600, accounts=2, envs=2, chain_envs=1,
                  la_gb=8, lake_gb=20, ledger_gb=1, ops_ru_m=20, ops_gb=2, search_units=2,
                  aca_vcpu_h=150, aca_req_m=1, dp_gb=50, own_subs=4, peer_gb=10,
                  rt_scans=6, rt_attacks=500, fn_always_ready=1, fw_gb=100,
                  lab_experiments=0, moves_drafted=25, signals=50, t3_cases=0, method_cycles=1,
                  commitments=1, detections=100,
                  gate_decoys=99, gate_cases=99, gate_repeats=3, gate_releases=1),
    "Team": dict(subs=50, resources=10_000, owners=100, cases=1_000, spend=400_000,
                 survey_calls=1_500, study_changes=40, exam_cases=1_350, accounts=4, envs=3, chain_envs=2,
                 la_gb=40, lake_gb=300, ledger_gb=5, ops_ru_m=200, ops_gb=10, search_units=4,
                 aca_vcpu_h=600, aca_req_m=10, dp_gb=500, own_subs=5, peer_gb=50,
                 rt_scans=8, rt_attacks=1_000, fn_always_ready=1, fw_gb=500,
                 lab_experiments=4, moves_drafted=250, signals=500, t3_cases=30, method_cycles=2,
                 commitments=4, detections=300,
                 gate_decoys=218, gate_cases=891, gate_repeats=3, gate_releases=1),
    "Enterprise": dict(subs=1000, resources=200_000, owners=2000, cases=20_000, spend=8_000_000,
                       survey_calls=30_000, study_changes=40, exam_cases=2_700, accounts=4, envs=3, chain_envs=2,
                       la_gb=400, lake_gb=4_000, ledger_gb=40, ops_ru_m=1_500, ops_gb=100, search_units=5,
                       aca_vcpu_h=3_000, aca_req_m=100, dp_gb=5_000, own_subs=8, peer_gb=500,
                       rt_scans=12, rt_attacks=2_000, fn_always_ready=2, fw_gb=5_000,
                       lab_experiments=10, moves_drafted=5_000, signals=10_000, t3_cases=100, method_cycles=4,
                       commitments=20, detections=1_000,
                       gate_decoys=218, gate_cases=891, gate_repeats=3, gate_releases=4),
}
for _s in SCENARIOS.values():
    _s["gate_runs"] = (_s["gate_decoys"] + _s["gate_cases"]) * _s["gate_repeats"] * _s["gate_releases"]

# Token workloads per *case* (W4): role, alias, contract, then calls per case, input tokens per call, the
# static prefix (tokens) that one explicit cache breakpoint covers (05 section 7: a session writes it on its
# first call, its later calls read it, and tokens written are billed at the write price instead of the input
# price) and output tokens per call.  One session per role per case.
CASE_WORK = [
    ("Detective", "reason", "investigate", dict(calls=10, tin=15_000, prefix=6_000, tout=1_500)),
    ("Skeptic", "judge", "investigate", dict(calls=4, tin=12_000, prefix=0, tout=1_000)),
    ("Economist", "reason", "investigate", dict(calls=4, tin=10_000, prefix=5_000, tout=1_000)),
    ("Diplomat", "reason", "converse", dict(calls=2, tin=6_000, prefix=3_000, tout=800)),
    ("Triage", "luna", "conduct", dict(calls=6, tin=3_000, prefix=1_500, tout=300)),
    ("Auditor", "judge", "govern", dict(calls=1, tin=10_000, prefix=0, tout=1_000)),
]
# The hub's access contracts (design 04 section 4.3): the aliases each lists, and its data class.  The euro worst
# case of a quota is priced at the dearest rate of the dearest alias, on the pools the environment may reach.
# The Claude model behind `judge-pub` is billed through the Marketplace with no price in the API, so Sol on
# Global stands in (UNVERIFIED); `judge-eu` is Mistral Large 3, a stand-in for "an independent-family model".
CONTRACT_ALIASES = {
    "study": {"triage", "reason", "embed", "batch"},
    "curate": {"judge-pub", "embed"},
    "survey": {"triage", "reason"},
    "investigate": {"reason", "judge-eu"},
    "experiment": {"reason"},
    "converse": {"triage", "reason"},
    "engineer": {"reason"},
    "govern": {"judge-eu", "reason", "embed"},
    "examine-pub": {"judge-pub", "judge-eu", "embed", "batch"},
    "examine-eu": {"judge-eu", "embed"},
    "forge": {"reason"},
    "conduct": {"triage", "reason", "embed"},
}
PUBLIC_CONTRACTS = {"study", "curate", "experiment", "examine-pub", "forge"}   # public or synthetic data: Global pools
NO_PROD_CONTRACTS = {"examine-pub", "forge"}   # synthetic estates never run in production: no PROD product (design 04 section 4.3)
# The pools each contract may reach in PROD (design 04 section 4.3); TEST and DEV carry synthetic data only and reach the public pools.
CONTRACT_POOLS = {
    "study": {"acia-global", "acia-flex"},
    "curate": {"acia-global"},
    "survey": {"acia-eu"},
    "investigate": {"acia-eu", "acia-judge-eu"},
    "experiment": {"acia-global"},
    "converse": {"acia-eu"},
    "engineer": {"acia-eu"},
    "govern": {"acia-eu", "acia-judge-eu"},
    "examine-pub": {"acia-global", "acia-flex", "acia-judge-eu"},
    "examine-eu": {"acia-eu", "acia-judge-eu"},
    "forge": {"acia-global"},
    "conduct": {"acia-eu"},
}
ENVIRONMENTS = ("prod", "test", "dev")
FIRST_PHASE = {"dev": 0, "prod": 2, "test": 3, "lab": 4}   # the phase of design 14 section 4 in which each environment first exists


def environments_present(s: dict) -> list[str]:
    """The contract environments a scenario creates: PROD and DEV always, TEST only where there is a TEST account.
    Pilot has none, so DEV carries the exams, the gates and the attacks (design 14 section 4, 11 section 3)."""
    return ["prod", "dev"] + (["test"] if s["accounts"] >= 3 else [])


ENV_FLOOR = {"test": 0.25, "dev": 0.10}      # design 04 section 4.3: TEST and DEV carry at least this share of production's quota
DAILY_SHARE = {"experiment": 0.10}            # a daily quota on the Experimenter: at most this share of the month in a day
# Peak calls in flight per contract (seeds): the overrun of a token limit is bounded by this times the largest call.
CONCURRENCY = {"study": 4, "curate": 2, "survey": 8, "investigate": 12, "experiment": 2, "converse": 6, "engineer": 4,
               "govern": 2, "examine-pub": 16, "examine-eu": 2, "forge": 4, "conduct": 4}
DEV_CONCURRENCY = 2
CALLS_PER_MINUTE_PER_SLOT = 2  # starting tokens-per-minute limit = concurrency x largest call x this
# Hosted-agent sessions per case: role, active minutes, idle timeout in minutes.  Each idle timeout is at least the
# role's p99 active time (design 05 section 5, Round 2: the platform deprovisions the compute when no request arrives
# within the timeout, so a leaf that returns at once and works on must not outlive it).  Whether idle time is billed
# is UNVERIFIED (the hosted-agents page shows active and idle states and states no idle price; the GA record says
# "you pay only for active execution"), so it is billed here, the conservative reading: a session then costs the
# larger of its active time and its idle timeout, because the timer starts at the last request.  A session is
# 0.5 vCPU and 1 GiB by default (05 section 5).
HOSTED_SESSIONS = [("Detective", 12, 20), ("Skeptic", 6, 10), ("Economist", 5, 10), ("Diplomat", 2, 15), ("Triage", 3, 5),
                   ("Auditor", 2, 5)]
HOSTED_H_PER_CASE = sum(max(a, t) for _, a, t in HOSTED_SESSIONS) / 60.0
HOSTED_ACTIVE_H_PER_CASE = sum(a for _, a, _ in HOSTED_SESSIONS) / 60.0
HOSTED_VCPU, HOSTED_GIB = 0.5, 1.0
SANDBOX_H_PER_CASE = 1.0      # one batched session-hour per case (typed query tools are preferred, 05 section 5; UNVERIFIED hour rounding)
RT_PER_ATTACK = dict(target=dict(tin=3_000, tout=600), attacker=dict(tin=1_500, tout=400), evaluator=dict(tin=3_000, tout=200))
FN_EXEC_PER_CASE = 150        # Durable Functions executions per case or exam case: leaf calls, completion events, record writes, timers
FN_REPLAY_FACTOR = 1.3        # orchestrator replays that bill as executions: UNVERIFIED until S-ORCH-1 (design 05 section 4)
FN_GB_S_PER_EXEC = 2.0        # a 2 GB instance for about a second
FN_READY_SHARE = 0.8          # share of production execution that runs on the always-ready instance (own rate, no free grant)
FLEX_SHARE = 0.8              # share of exam, gate and red-team tokens served on the Flex tier; the rest is re-run on Global Standard after a 429 or a deadline (UNVERIFIED)
PII_RECORDS_PER_CALL = 10     # 1,000-character records of free text pseudonymised in the tool services per Surveyor or Diplomat call
QUOTA_HEADROOM = 1.5          # monthly contract quota = planned tokens x this
QUOTA_CAP_LIMIT = 2.0         # --check fails if the summed forecast-equivalent cap exceeds this multiple of the token plan
LABOUR_RATE_EUR = 75.0        # stated seed for the labour sensitivity, EUR per hour
LABOUR_HOURS = (20, 40, 80, 160)
GATE_REVIEW_HOURS = 6.0       # a person reads the failed critical cases and a fifth of the passed ones and labels the judges' sample, per gated domain-release (seed)
# Inventory (design 03 section 5, 04 section 6, 07 section 6.1): vaults, endpoints and the stores of a Foundry account.
SIGNING_PARTIES = 6           # Approval service, Policy service, broker, runner, Verifier, Audit Writer: one vault each per chain environment
SECRETS_VAULTS_PER_ENV = 1
REGISTRY_VAULTS = 1           # the pipeline's signing key and the registry
PE_PER_ACCOUNT = 4            # Foundry account, AI Search, Cosmos DB, Storage (the Foundry file and blob store)
PE_PER_SPINE_ENV = 3          # the spine's storage account: blob, queue, table
PE_PER_CHAIN_ENV = 1          # the chain's queue storage account `stchain` (queue subresource), design 07 section 3.3
PE_BASE = 8                   # registry, ledger store, recovery lake (two regions), operational Cosmos DB, monitoring, Key Vault-less services
FOUNDRY_FILE_GB = 5           # files and intermediate blobs of one Foundry account (agent files, vector-store staging), Hot ZRS
ATLAS_QUERIES_PER_CASE = 20   # Atlas retrievals per case (Detective, Economist, Diplomat), each through the semantic ranker
LAB_EUR_PER_EXPERIMENT = 25.0 # the pre-deploy cost cap of one Lab recipe (07 section 8), a seed
FORGER_TOKENS = dict(tin=30_000, tout=8_000)   # one synthetic estate (five cases) per call
CASES_PER_ESTATE = 5
INTER_REGION_EUR_PER_GB = 0.0176              # USD 0.02 per GB within Europe at the snapshot's rate (vendor bandwidth page, checked by Round-2 reviewer C); not in the snapshot
COPY_DELTA_SHARE_PER_HOUR = 0.002             # share of the operational store that changes and is copied each hour (seed)
# Content Safety text records (1,000 characters each).  The hub's llm-content-safety policy screens a response in
# windows of 1,000 characters by default, which can overlap, and a prompt in windows of 10,000 (Learn).  Baseline:
# untrusted free text is screened ONCE, where it enters (the tool service, or the hub on the tool's response), and
# the verdict is cached by content hash; the hub does not re-screen the whole accumulated prompt on every call.
# Screening every prompt on every call is a named sensitivity (Model.scenario(screen_all_prompts=True)).
CS_WINDOW, CS_OVERLAP = 1_000, 100
CHARS_PER_TOKEN = 4
CS_TOOL_RESPONSES_PER_CASE = 20   # tool results with free text (tags, names, invoice lines, directory fields)
CS_TOOL_RESPONSE_CHARS = 3_000
CS_REPLIES_PER_CASE = 2           # owner replies screened on the way in
CS_REPLY_CHARS = 1_000
CS_SURVEY_CHARS = 3_000           # free text per Surveyor call
CS_FEED_CHARS = 2_000             # one release-feed item
CS_STUDY_DOCS_PER_CHANGE, CS_STUDY_DOC_CHARS = 12, 30_000   # documents the Scholar reads (chunked in the sanitiser)

# Labels of the token lines (the report groups the workloads by these).
L_CASES = "Cases (W4) on the EU Data Zone"
L_WATCH = "Watch (W1): triage of the release feed"
L_STUDY = "Study (W2): Scholar, Cartographer, Librarian"
L_SURVEY = "Survey (W3): Surveyor on changes"
L_DREAM = "Dream (W7): nightly consolidation"
L_EXAM = "Continuous exams (W8) on synthetic estates"
L_GATE = "Release gates: G3 decoys and G4 comparison runs (design 10 section 4)"
L_RT = "Red teaming (L5): attacker, target and evaluator (UNVERIFIED seed)"
L_EMB = "Embeddings (Atlas releases and retrieval)"
L_OTHER = "Other workflows: engineer, signals (W3b), commitments (W5), self-watch (W9), experiments (W6), method learning (W10), forger, T3 exam"
L_DEV = "Development and CI smoke tests (every contract, dev environment)"
DEV_CALLS = 600               # smoke-test calls a month per contract in the dev environment (about 0.6 M tokens)

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
    "blob_hot_gzrs": (0.0405, "Retail Prices API, 2026-10-31: Storage, General Block Blob v2, Hot GZRS, Sweden Central, first tier; not in the snapshot"),
}


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
            raise LookupError(f"{len(hits)} meters ({vals}) for selector {sel}; add pick='max' or narrow it")
        v = vals[-1] if pick == "max" else vals[0] if pick == "min" else vals[0]
        self.used[sel] = (v, hits[0]["unitOfMeasure"])
        self._cache[key] = v
        return v


def per_m(price_1k: float) -> float:
    return price_1k * 1000.0


def cs_records(chars: float) -> int:
    """Content Safety text records (1,000 characters each) for a text screened in overlapping windows."""
    if chars <= 0:
        return 0
    return max(1, math.ceil(max(0.0, chars - CS_OVERLAP) / (CS_WINDOW - CS_OVERLAP)))


class Model:
    def __init__(self, prices: Prices, **knobs):
        self.p = prices
        # the named sensitivities of the report switch these; the baseline is the default of each
        self.k = dict(flex_share=FLEX_SHARE, replay=FN_REPLAY_FACTOR, screen_all=False, screen_tests=True, hosted_idle=True,
                      gate_scale=1.0, ranker=True)
        unknown = set(knobs) - set(self.k)
        if unknown:
            raise KeyError(f"unknown knob {sorted(unknown)}")
        self.k.update(knobs)

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
    def tokens_cost(price: dict, calls: float, tin: float, prefix: float, tout: float,
                    sessions: float = 1.0, cw_per_call: bool = False) -> float:
        """`prefix` is the static prefix (tokens) that one explicit cache breakpoint covers (design 05 section 7).
        A session writes it on its first call, billed at the write price instead of the input price, and its later
        calls read it at the cached price; the rest of every call is plain input.  `cw_per_call` is the pessimistic
        reading in which every call rewrites the prefix (the cache never hits)."""
        prefix = min(prefix, tin)
        writes = calls if cw_per_call else min(calls, sessions)
        reads = calls - writes
        plain = calls * (tin - prefix) * price["inp"]
        return (plain + writes * prefix * price["cw"] + reads * prefix * price["cd"] + calls * tout * price["out"]) / 1e6

    def cost_of(self, x: dict) -> float:
        return self.tokens_cost(x["price"], x["calls"], x["tin"], x["prefix"], x["tout"], x["sessions"])

    def exam_price(self, alias: str) -> dict:
        """Exam, gate and red-team tokens: `flex_share` on the Flex tier, the rest re-run on Global Standard after
        a 429 or a missed deadline (design 10 section 2, L4: Flex has no fallback and no SLA)."""
        sh = self.k["flex_share"]
        f, g = self.alias(alias, "Gl", "Flex"), self.alias(alias, "Gl", "Std")
        return {key: sh * f[key] + (1 - sh) * g[key] for key in ("inp", "out", "cd", "cw")}

    def case_cost(self, zone: str = "DZ", svc_class: str = "Std", detail: bool = False, cw_per_call: bool = False,
                  no_cache: bool = False):
        total, rows = 0.0, []
        for role, alias, _contract, w in CASE_WORK:
            w = dict(w, prefix=0) if no_cache else w
            c = self.tokens_cost(self.alias(alias, zone, svc_class), **w, cw_per_call=cw_per_call)
            total += c
            rows.append((role, alias, c))
        return (total, rows) if detail else total

    def workloads(self, s: dict) -> list[dict]:
        """Every token workload of a scenario with its contract and environment (prod, test or dev).  The euro
        lines and the hub quotas both derive from this list, so a quota can never drift from the plan it caps."""
        W: list[dict] = []
        # Where the exams, the gates, the attacks and method learning run: in TEST, or in DEV where the scenario has
        # no TEST account (Pilot; design 14 section 4).  `kind` keeps the workload's purpose whichever environment holds it.
        tenv = "test" if "test" in environments_present(s) else "dev"

        def add(label, contract, env, price, calls, tin, prefix, tout, sessions):
            W.append(dict(label=label, contract=contract, env=(tenv if env == "test" else env), kind=env, price=price,
                          calls=calls, tin=tin, prefix=prefix, tout=tout, sessions=sessions))

        cases, ch, calls = s["cases"], s["study_changes"], s["survey_calls"]
        sol_eu, luna_eu = self.gpt6("6.1-sol", "DZ"), self.gpt6("6-luna", "DZ")
        sol_gl, luna_gl = self.gpt6("6.1-sol", "Gl"), self.gpt6("6-luna", "Gl")
        judge_eu, judge_gl = self.mistral_large3("DZ"), self.mistral_large3("Gl")
        for role, alias, contract, w in CASE_WORK:
            add(L_CASES, contract, "prod", self.alias(alias, "DZ"), cases * w["calls"], w["tin"], w["prefix"], w["tout"], cases)
        feed_items = 150 * 30
        add(L_WATCH, "study", "prod", luna_gl, feed_items, 1_500, 750, 100, 30)          # one burst a day shares its prefix
        add(L_STUDY, "study", "prod", sol_gl, ch * 12, 20_000, 6_000, 2_000, ch)
        add(L_STUDY, "study", "prod", sol_gl, ch * 4, 15_000, 4_000, 1_500, ch)
        add(L_STUDY, "curate", "prod", sol_gl, ch * 4, 15_000, 4_000, 1_500, ch)
        bursts = 24 * 30                                                                   # an hourly refresh: one session per burst
        add(L_SURVEY, "survey", "prod", luna_eu, 0.8 * calls, 8_000, 2_000, 600, min(0.8 * calls, bursts))
        add(L_SURVEY, "survey", "prod", sol_eu, 0.2 * calls, 8_000, 2_000, 600, min(0.2 * calls, bursts))
        add(L_DREAM, "govern", "prod", sol_eu, 30 * (5 + cases / 200.0), 20_000, 5_000, 2_000, 30)
        # exams and gates run W4 on synthetic estates in the TEST environment (DEV where there is none): Flex where it is
        # available, plus 30 % judge work (two families on G5) on the `examine-pub` contract
        gate_total = s["gate_runs"] * self.k["gate_scale"]
        for label, runs in ((L_EXAM, s["exam_cases"]), (L_GATE, gate_total)):
            for role, alias, contract, w in CASE_WORK:
                x = dict(label=label, contract=contract, env=tenv, kind="test", price=self.exam_price(alias), calls=runs * w["calls"],
                         tin=w["tin"], prefix=w["prefix"], tout=w["tout"], sessions=runs)
                W.append(x)
                W.append(dict(x, contract="examine-pub", calls=0.3 * x["calls"], sessions=0.3 * x["sessions"]))
        n_attacks = s["rt_scans"] * s["rt_attacks"]
        rt = RT_PER_ATTACK
        add(L_RT, "investigate", "test", self.exam_price("reason"), n_attacks, rt["target"]["tin"], 0, rt["target"]["tout"], 0)
        add(L_RT, "examine-pub", "test", self.exam_price("luna"), n_attacks, rt["attacker"]["tin"], 0, rt["attacker"]["tout"], 0)
        add(L_RT, "examine-pub", "test", self.exam_price("luna"), n_attacks, rt["evaluator"]["tin"], 0, rt["evaluator"]["tout"], 0)
        embed = self.p.get("Foundry Models", product="Azure OpenAI", sku="text-embedding-3-large-regional") * 1000.0
        emb_tokens = 5_000_000 * 4 + cases * 50 * 300
        add(L_EMB, "curate", "prod", dict(inp=embed, out=0.0, cd=embed, cw=0.0), emb_tokens / 8_000, 8_000, 0, 0, 1)   # requests of 8,000 tokens
        # the roles and workflows that the first model left out (Round 2, C-06)
        moves = s["moves_drafted"]
        add(L_OTHER, "engineer", "prod", sol_eu, moves * 5, 15_000, 4_000, 2_000, moves)
        add(L_OTHER, "conduct", "prod", luna_eu, s["signals"], 6_000, 0, 400, s["signals"])          # W3b: a triage call only when the check is ambiguous
        add(L_OTHER, "investigate", "prod", sol_eu, s["commitments"] * 8, 20_000, 5_000, 1_500, s["commitments"])   # W5: the Economist's proposal and re-price
        add(L_OTHER, "govern", "prod", judge_eu, s["detections"], 6_000, 0, 800, s["detections"])    # W9: the Auditor's triage of detections
        add(L_OTHER, "experiment", "prod", sol_gl, s["lab_experiments"] * 4, 20_000, 5_000, 2_000, s["lab_experiments"])   # W6: plan and analysis
        add(L_OTHER, "examine-pub", "test", self.exam_price("reason"), s["method_cycles"] * 30, 20_000, 5_000, 2_000, s["method_cycles"] * 3)   # W10
        forged = (s["exam_cases"] + gate_total) / (CASES_PER_ESTATE * s["gate_repeats"])
        add(L_OTHER, "forge", "test", judge_gl, forged, FORGER_TOKENS["tin"], 0, FORGER_TOKENS["tout"], forged)   # another model family than the investigators'
        add(L_OTHER, "examine-eu", "prod", judge_eu, s["t3_cases"] * 3, 12_000, 0, 1_000, s["t3_cases"] * 3)
        for name in CONTRACT_ALIASES:
            add(L_DEV, name, "dev", self.rep_price(name), DEV_CALLS, 800, 0, 200, DEV_CALLS)
        return W

    def rep_price(self, contract: str) -> dict:
        """A representative price for a contract's smoke tests: the strongest alias it lists, on the public pools
        (DEV carries synthetic data only)."""
        a = CONTRACT_ALIASES[contract]
        if "reason" in a or "judge-pub" in a:
            return self.gpt6("6.1-sol", "Gl")
        if "triage" in a:
            return self.gpt6("6-luna", "Gl")
        return self.mistral_large3("DZ")

    def dearest(self, contract: str, env: str) -> float:
        """The dearest rate (EUR per million tokens, input or output) among the aliases a contract lists, on the
        pools its environment may reach: estate contracts in production use the EU Data Zone, everything else
        (public contracts, and TEST and DEV, which carry synthetic data only) the Global pools."""
        zone = "Gl" if (contract in PUBLIC_CONTRACTS or env != "prod") else "DZ"
        prices = []
        for a in CONTRACT_ALIASES[contract]:
            if a == "triage":
                prices.append(self.alias("luna", zone))
            elif a == "reason":
                prices.append(self.alias("reason", zone))
            elif a == "judge-eu":
                prices.append(self.alias("judge", "DZ"))
            elif a == "judge-pub":
                prices.append(self.alias("reason", "Gl"))      # stand-in for the Claude model (UNVERIFIED price)
            elif a == "batch":
                prices.append(self.alias("reason", "Gl", "Flex"))
        return max(max(p["inp"], p["out"]) for p in prices)

    def quotas(self, s: dict, wl: list[dict] | None = None) -> list[dict]:
        """Monthly token quota per (contract, environment): the plan x QUOTA_HEADROOM, for every contract that has
        planned work in that environment.  TEST and DEV carry at least ENV_FLOOR of production's plan (design 04
        section 4.3), or their own planned work where that is larger.  Each row also gives the forecast-equivalent
        euros (the quota at the contract's own blended price), the worst case (the quota at the dearest rate the
        contract's aliases allow), a starting tokens-per-minute limit and the in-flight overrun a limit can suffer."""
        wl = wl or self.workloads(s)
        present = environments_present(s)
        tenv = "test" if "test" in present else "dev"
        agg: dict[tuple[str, str], list[float]] = {}
        for x in wl:
            a = agg.setdefault((x["contract"], x["env"]), [0.0, 0.0, 0.0])
            a[0] += x["calls"] * (x["tin"] + x["tout"])
            a[1] += self.cost_of(x)
            a[2] = max(a[2], x["tin"] + x["tout"])
        rows = []
        for c in CONTRACT_ALIASES:
            prod = agg.get((c, "prod"))
            for e in ENVIRONMENTS:
                if e not in present:
                    continue
                own = agg.get((c, e))
                floor = ENV_FLOOR.get(e, 0.0) * (prod[0] if prod else 0.0)
                planned = max(own[0] if own else 0.0, floor)
                if planned <= 0:
                    continue
                ref = own if own and own[0] else prod
                blended = ref[1] / ref[0]
                big = ref[2]
                q = math.ceil(planned * QUOTA_HEADROOM / 1e6) * 1e6
                slot = (DEV_CONCURRENCY if (e == "dev" and tenv != "dev") else CONCURRENCY[c]) * big
                dear = self.dearest(c, e)
                rows.append(dict(contract=c, env=e, planned_tokens=planned, quota_tokens=q, has_work=bool(own and own[0]),
                                 own_eur=own[1] if own else 0.0,
                                 planned_eur=planned * blended, cap_eur=q * blended, worst_eur=q * dear / 1e6,
                                 tpm=slot * CALLS_PER_MINUTE_PER_SLOT, overrun_tokens=slot, overrun_eur=slot * dear / 1e6,
                                 daily=(q * DAILY_SHARE[c] if c in DAILY_SHARE else None)))
        return rows

    # -- one scenario ------------------------------------------------------
    def scenario(self, name: str, hub: str = "shared") -> dict:
        s = SCENARIOS[name]
        P, L = self.p, []

        def add(group: str, label: str, eur: float, note: str = "") -> None:
            L.append(dict(group=group, label=label, eur=round(eur, 2), note=note))

        # tokens -----------------------------------------------------------
        k = self.k
        calls = s["survey_calls"]
        feed_items = 150 * 30
        case_eu = self.case_cost("DZ", "Std")
        wl = self.workloads(s)
        gate_total = s["gate_runs"] * k["gate_scale"]
        test_runs = s["exam_cases"] + gate_total          # W4 runs on synthetic estates, in the TEST environment
        notes = {
            L_CASES: f"{s['cases']} cases at EUR {case_eu:.3f} of marginal tokens each; cache written once per session, first call reads nothing",
            L_WATCH: "public data, Global; the day's burst shares one cached prefix",
            L_STUDY: "public data, Global Standard",
            L_SURVEY: "80% Luna, 20% Sol, EU Data Zone; one cached session per hourly burst",
            L_DREAM: "estate lessons, EU Data Zone (flex is Global only)",
            L_EXAM: f"{s['exam_cases']:,} case-runs, {k['flex_share']:.0%} on Flex and the rest on Global Standard, plus 30% for judges",
            L_GATE: (f"{s['gate_releases']} gated domain-release(s) a month of ({s['gate_decoys']} decoys + {s['gate_cases']} comparison cases) "
                     f"x {s['gate_repeats']} runs = {gate_total:,.0f} case-runs; baselines frozen and reused"),
            L_RT: f"{s['rt_scans']} scans of {s['rt_attacks']:,} attacks, {k['flex_share']:.0%} on Flex; the self-hosted harness pays the same tokens",
            L_EMB: "weekly index rebuild plus retrieval",
            L_OTHER: "engineer (5 calls per drafted Move), W3b triage, W5 re-pricing, W9 Auditor triage, W6 plan and analysis, W10 post-mortems, "
                     "forger on another family (Mistral Large 3 stands in), T3 judge",
            L_DEV: f"{DEV_CALLS:,} calls of 1,000 tokens on each of {len(CONTRACT_ALIASES)} contracts, on the strongest alias each lists",
        }
        order: list[str] = []
        for x in wl:
            if x["label"] not in order:
                order.append(x["label"])
        for lab in order:
            add("Tokens", lab, sum(self.cost_of(x) for x in wl if x["label"] == lab), notes[lab])
        cs = P.get("Foundry Tools", product="Content Safety", sku="Standard", meter="Standard Text Records")
        per_case = CS_TOOL_RESPONSES_PER_CASE * cs_records(CS_TOOL_RESPONSE_CHARS)
        routes = {
            "tool responses and owner replies, cases": s["cases"] * (per_case + CS_REPLIES_PER_CASE * cs_records(CS_REPLY_CHARS)),
            "tool responses, exam and gate runs": (test_runs * per_case) if k["screen_tests"] else 0,
            "Surveyor and fast-signal free text": (calls + s["signals"]) * cs_records(CS_SURVEY_CHARS),
            "release-feed items": feed_items * cs_records(CS_FEED_CHARS),
            "documents read by the Scholar": s["study_changes"] * CS_STUDY_DOCS_PER_CHANGE * cs_records(CS_STUDY_DOC_CHARS),
            "attack responses": s["rt_scans"] * s["rt_attacks"] * cs_records(2_400),
        }
        records = sum(routes.values())
        all_prompts = sum(x["calls"] * (x["tin"] + x["tout"]) * CHARS_PER_TOKEN / 1000.0 for x in wl if x["label"] not in (L_EMB, L_DEV))
        if k["screen_all"]:
            records = all_prompts
        add("Tokens", "Content Safety screening of untrusted text (Standard tier: no free allowance)", records / 1000.0 * cs,
            f"{records:,.0f} records of 1,000 characters, screened once where the text enters (windows of {CS_WINDOW:,} with {CS_OVERLAP} overlap); "
            f"screening every prompt on every call would be {all_prompts:,.0f}")
        pii = (calls + 2 * s["cases"]) * PII_RECORDS_PER_CALL
        add("Tokens", "Personal-data pseudonymisation (Language PII) in the tool services", pii / 1000.0 * MANUAL["language_pii_per_1k"][0],
            f"{pii:,.0f} records at the research rate, UNVERIFIED")

        # compute ------------------------------------------------------------
        hv = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted vCPU Usage")
        hm = P.get("Foundry Tools", product="Foundry Agents", sku="Hosted", meter="Hosted Memory Usage")
        per_case_h = HOSTED_H_PER_CASE if k["hosted_idle"] else HOSTED_ACTIVE_H_PER_CASE
        hosted_h = (s["cases"] + test_runs) * per_case_h + s["study_changes"] * 1.0 + calls * 5 / 60.0 + 30 * 0.5
        add("Compute", "Hosted agents: sessions, active plus idle timeout", hosted_h * (hv * HOSTED_VCPU + hm * HOSTED_GIB),
            f"{hosted_h:,.0f} h at {HOSTED_VCPU} vCPU and {HOSTED_GIB:g} GiB; {per_case_h:.2f} h per case-run; idle billing UNVERIFIED, billed here")
        sbx = P.get("Azure Container Apps", product="Azure Container Apps", sku="Dynamic Sessions", meter="Dynamic Sessions")
        sbx_h = (s["cases"] + test_runs) * SANDBOX_H_PER_CASE
        add("Compute", "Sandbox sessions for model-written analysis, batched", sbx_h * sbx,
            f"{sbx_h:,.0f} session-hours at the dynamic-sessions rate; hour rounding UNVERIFIED")
        fb = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Baseline")
        fr = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Execution Time")
        fre = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Total Executions")
        fx = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Execution Time", pick="max")
        fe = P.get("Functions", product="Flex Consumption", sku="On Demand", meter="On Demand Total Executions", pick="max")
        prod_execs = (s["cases"] * FN_EXEC_PER_CASE + s["subs"] * 30 * 4) * k["replay"]
        test_execs = test_runs * FN_EXEC_PER_CASE * k["replay"]

        def on_demand(execs: float) -> float:
            """On-demand cost in one subscription after its monthly grant of 100,000 GB-s and 250,000 executions."""
            return max(0.0, execs * FN_GB_S_PER_EXEC - 100_000) * fx + max(0.0, execs - 250_000) / 10.0 * fe

        ready = prod_execs * FN_READY_SHARE
        fn_ready = ready * FN_GB_S_PER_EXEC * fr + ready / 10.0 * fre
        add("Compute", "Durable Functions spine (Flex Consumption): always-ready instance and executions, production and test",
            s["fn_always_ready"] * 2 * 3600 * HOURS * fb + fn_ready + on_demand(prod_execs * (1 - FN_READY_SHARE)) + on_demand(test_execs),
            f"{s['fn_always_ready']} always-ready 2 GB instance(s) in production only; {prod_execs:,.0f} production executions ({FN_READY_SHARE:.0%} on the "
            f"always-ready instance at its own rates, no free grant) and {test_execs:,.0f} on-demand test executions, each environment in its own subscription's "
            f"grant; replays counted at x{k['replay']}, UNVERIFIED until S-ORCH-1")
        add("Compute", "Durable Functions task-hub storage (queue polling at 10 s or less)",
            MANUAL["spine_task_hub_storage"][0] * (1 + s["cases"] / 5000.0) + (s["envs"] - 1) * 1.0,
            "estimate; queue and table meters are not in the snapshot; the scale-to-zero environments cost about a euro each")
        lab = s["lab_experiments"] * LAB_EUR_PER_EXPERIMENT
        add("Compute", "Lab experiments: two-day resources under the pre-deploy cost cap", lab,
            f"{s['lab_experiments']} recipes at the EUR {LAB_EUR_PER_EXPERIMENT:.0f} cap each (a seed; the cap is the upper bound of one recipe)")
        vcpu_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard vCPU Active Usage")
        mem_s = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Memory Active Usage")
        req = P.get("Azure Container Apps", product="Azure Container Apps", sku="Standard", meter="Standard Requests")
        grant_v, grant_m, grant_r = 180_000 * s["own_subs"] / 4, 360_000 * s["own_subs"] / 4, 2.0 * s["own_subs"] / 4
        vcpu_sec, gib_sec = s["aca_vcpu_h"] * 3600, s["aca_vcpu_h"] * 3600 * 2
        add("Compute", "Container Apps: tool services, execution plane, adapters",
            max(0, vcpu_sec - grant_v) * vcpu_s + max(0, gib_sec - grant_m) * mem_s + max(0, s["aca_req_m"] - grant_r) * req,
            f"{s['aca_vcpu_h']} vCPU-hours, 2 GiB each, after the free grants")

        # data and observability ----------------------------------------------
        inv = self.inventory(s)
        srch = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Basic", meter="Basic Unit")
        add("Data", "AI Search Basic: one per private Foundry account (standard setup); the Atlas index shares production's",
            s["search_units"] * srch * HOURS,
            f"{s['accounts']} accounts, {s['search_units']} unit(s); direct hybrid retrieval is the baseline, Foundry IQ agentic retrieval is off and unpriced; "
            "the services are created on day zero (design 14), before their accounts, and are priced by phase in the floor table")
        sem = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Semantic Ranker", meter="Semantic Ranker queries")
        atlas_q = s["cases"] * ATLAS_QUERIES_PER_CASE + s["study_changes"] * 100 + calls * 2
        add("Data", "AI Search semantic ranker on Atlas queries (1,000 free a month)",
            (max(0.0, atlas_q - 1000) / 1000.0 * sem) if k["ranker"] else 0.0,
            f"{atlas_q:,.0f} queries; switched off where the exam shows no gain (lever 13)")
        ru = P.get("Azure Cosmos DB", product="Azure Cosmos DB serverless", sku="RUs", meter="1M RUs")
        st = P.get("Azure Cosmos DB", product="Azure Cosmos DB", sku="RUs", meter="Data Stored")
        acc = s["accounts"]
        add("Data", "Cosmos DB serverless: operational store and one account per Foundry account", (s["ops_ru_m"] + 20 * acc) * ru + (s["ops_gb"] + 5 * acc) * st,
            f"{s['ops_ru_m']} M request units and {s['ops_gb']} GB, plus 20 M and 5 GB for each of {acc} Foundry accounts")
        cool = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Cool ZRS", meter="Cool ZRS Data Stored", pick="max")
        hot = P.get("Storage", product="General Block Blob v2 Hierarchical Namespace", sku="Hot ZRS", meter="Hot ZRS Data Stored", pick="max")
        add("Data", "Foundry file and blob storage: one store per private account (Hot ZRS)", acc * FOUNDRY_FILE_GB * hot,
            f"{acc} accounts x {FOUNDRY_FILE_GB} GB of agent files and intermediate blobs; transactions are cents")
        gzrs = MANUAL["blob_hot_gzrs"][0]
        add("Data", "Cost lake (Cool ZRS) and audit ledger (Hot GZRS)", s["lake_gb"] * cool + s["ledger_gb"] * gzrs,
            f"{s['lake_gb']} GB lake; {s['ledger_gb']} GB ledger in a GZRS account at EUR {gzrs} a GB-month ({MANUAL['blob_hot_gzrs'][1]})")
        rec_gb = (35 * s["ops_gb"] + s["ledger_gb"]) * 2
        add("Data", "Recovery lake: hourly exports and daily snapshots in two EU regions (35-day retention)", rec_gb * cool,
            f"{rec_gb:,.0f} GB over both copies at the Cool ZRS price")
        copy_gb = 30 * (s["ops_gb"] + s["ledger_gb"]) + 24 * 30 * COPY_DELTA_SHARE_PER_HOUR * s["ops_gb"]
        add("Data", "Recovery copies: inter-region transfer of the daily snapshot and the hourly deltas", copy_gb * INTER_REGION_EUR_PER_GB,
            f"{copy_gb:,.0f} GB a month at EUR {INTER_REGION_EUR_PER_GB} a GB (Retail Prices API, Bandwidth, inter-region, 2026-10-31); write operations are cents")
        acr_day = P.get("Container Registry", product="Container Registry", sku="Premium", meter="Premium Registry Unit")
        add("Data", "Container Registry Premium (private pull)", acr_day * DAYS, "one registry")
        pe_h = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard", meter="Standard Private Endpoint")
        pe_gb = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard",
                      meter="Standard Data Processed - Egress", pick="max")
        add("Network", "Private endpoints (hourly)", inv["pe"] * pe_h * HOURS,
            f"{inv['pe']} endpoints: {PE_PER_ACCOUNT} per private Foundry account, {inv['vaults']} vaults, {PE_PER_SPINE_ENV} per spine environment, {PE_PER_CHAIN_ENV} per chain environment, {PE_BASE} shared")
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
        add("Security", "Defender for Resource Manager and Key Vault (default tier)", s["own_subs"] * drm * HOURS + inv["vaults"] * dkv * HOURS,
            f"{s['own_subs']} subscriptions, {inv['vaults']} vaults ({s['envs']} secrets, {REGISTRY_VAULTS} registry, {SIGNING_PARTIES} signing parties in each of {s['chain_envs']} chain environment(s))")

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
        work = [r for r in q if r["has_work"]]
        host_rate = hv * HOSTED_VCPU + hm * HOSTED_GIB
        eval_eur = (sum(self.cost_of(x) for x in wl if x["kind"] == "test")
                    + test_runs * per_case_h * host_rate + test_runs * SANDBOX_H_PER_CASE * sbx + on_demand(test_execs)
                    + (routes["tool responses, exam and gate runs"] + routes["attack responses"]) / 1000.0 * cs)
        cases_eur = (sum(self.cost_of(x) for x in wl if x["label"] == L_CASES)
                     + s["cases"] * per_case_h * host_rate + s["cases"] * SANDBOX_H_PER_CASE * sbx
                     + routes["tool responses and owner replies, cases"] / 1000.0 * cs)
        gate = dict(runs=gate_total, eur=sum(self.cost_of(x) for x in wl if x["label"] == L_GATE),
                    review_hours=GATE_REVIEW_HOURS * s["gate_releases"])
        return dict(name=name, hub=hub, lines=L, groups={g: round(v, 2) for g, v in groups.items()}, total=round(total, 2),
                    per_case=round(total / s["cases"], 2), per_sub=round(total / s["subs"], 2),
                    breakeven_pct=round(100.0 * total / s["spend"], 2), params=s, quotas=q, inventory=inv, gate=gate,
                    eval_eur=round(eval_eur, 2), cases_eur=round(cases_eur, 2),
                    eval_sessions_eur=round(test_runs * per_case_h * host_rate, 2),
                    eval_idle_eur=round(test_runs * max(per_case_h - HOSTED_ACTIVE_H_PER_CASE, 0.0) * host_rate, 2),
                    plan_eur=round(sum(r["own_eur"] for r in work), 2), cap_eur=round(sum(r["cap_eur"] for r in work), 2),
                    worst_eur=round(sum(r["worst_eur"] for r in work), 2))

    @staticmethod
    def inventory(s: dict) -> dict:
        """What the floor is made of: environments, Foundry accounts, Search units, vaults and private endpoints."""
        vaults = s["envs"] * SECRETS_VAULTS_PER_ENV + REGISTRY_VAULTS + s["chain_envs"] * SIGNING_PARTIES
        pe = (PE_PER_ACCOUNT * s["accounts"] + vaults + PE_PER_SPINE_ENV * s["envs"] + PE_PER_CHAIN_ENV * s["chain_envs"] + PE_BASE)
        return dict(accounts=s["accounts"], search_units=s["search_units"], envs=s["envs"], chain_envs=s["chain_envs"],
                    vaults=vaults, pe=pe)

    def phase_floor(self, name: str) -> list[dict]:
        """The idle floor of each phase of design 14 section 4: environments are created in the phase that needs
        them, except the AI Search services, which are created on day zero (a deliberate idle meter)."""
        s, P = SCENARIOS[name], self.p
        srch = P.get("Azure Cognitive Search", product="Azure AI Search", sku="Basic", meter="Basic Unit")
        pe_h = P.get("Virtual Network", region="Global", product="Virtual Network Private Link", sku="Standard", meter="Standard Private Endpoint")
        drm = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Resource Manager", sku="Per node Std", meter="Per node Std Node")
        dkv = P.get("Microsoft Defender for Cloud", product="Microsoft Defender for Key Vault", sku="Per node Std", meter="Per node Std Node")
        fb = P.get("Functions", product="Flex Consumption", sku="Always Ready", meter="Always Ready Baseline")
        acr_day = P.get("Container Registry", product="Container Registry", sku="Premium", meter="Premium Registry Unit")
        first = FIRST_PHASE
        present = ["dev", "prod"] + (["test"] if s["accounts"] >= 3 else []) + (["lab"] if s["accounts"] >= 4 else [])
        spine_all = [e for e in present if e != "lab"]
        chain_all = ["prod"] + (["test"] if s["chain_envs"] >= 2 and "test" in present else [])
        extra_units = s["search_units"] - len(present)           # the larger scenarios give production more than one unit
        rows = []
        for label, p in (("0 Foundation", 0), ("1 Study", 1), ("2 Survey and investigate, in shadow", 2),
                         ("3 Brief, approve, act", 3), ("4 The Lab and learning", 4)):
            exist = [e for e in present if first[e] <= p]
            spine = [e for e in spine_all if first[e] <= p]
            chain = [e for e in chain_all if e in exist and p >= 3]
            vaults = len(spine) * SECRETS_VAULTS_PER_ENV + REGISTRY_VAULTS + len(chain) * SIGNING_PARTIES
            pe = (PE_PER_ACCOUNT * len(exist) + vaults + PE_PER_SPINE_ENV * len(spine) + PE_PER_CHAIN_ENV * len(chain) + PE_BASE)
            units_missing = sum(1 + (extra_units if e == "prod" else 0) for e in present if e not in exist)
            floor = (s["search_units"] * srch * HOURS + pe * pe_h * HOURS + vaults * dkv * HOURS
                     + s["own_subs"] * len(exist) / len(present) * drm * HOURS + acr_day * DAYS
                     + (s["fn_always_ready"] * 2 * 3600 * HOURS * fb if "prod" in exist else 0.0))
            rows.append(dict(phase=label, envs=exist, vaults=vaults, pe=pe, floor=floor, early_units=units_missing,
                             early_eur=units_missing * srch * HOURS))
        return rows

    def monthly_sensitivities(self) -> list[tuple[str, dict[str, float]]]:
        """The change in the monthly total, per scenario, when one assumption moves (shared hub)."""
        variants = [
            ("Exam, gate and red-team tokens all on Global Standard (no Flex)", dict(flex_share=0.0)),
            ("Twice as many gated domain-releases a month", dict(gate_scale=2.0)),
            ("The hub screens every prompt on every call with Content Safety", dict(screen_all=True)),
            ("Content Safety applied to the safety exams and attacks only, not to the capability exams and gates", dict(screen_tests=False)),
            ("Hosted-agent idle time not billed (the GA record's wording)", dict(hosted_idle=False)),
            ("Orchestrator replays bill twice the executions", dict(replay=2.0)),
            ("Direct hybrid retrieval only: the semantic ranker off (lever 13)", dict(ranker=False)),
        ]
        base = {n: self.scenario(n)["total"] for n in SCENARIOS}
        out = []
        for label, kn in variants:
            m = Model(self.p, **{**self.k, **kn})
            out.append((label, {n: m.scenario(n)["total"] - base[n] for n in SCENARIOS}))
        return out

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
            for role, alias, _contract, w in CASE_WORK:
                pr = price if alias == "reason" else self.alias(alias, zone)
                tot += self.tokens_cost(pr, **w)
            return tot
        return [("Baseline: one case on the EU Data Zone, cache written once per session", base),
                ("Cache written on every call (the pessimistic reading)", self.case_cost("DZ", "Std", cw_per_call=True)),
                ("The same case on Global (not allowed for estate data: the price of residency)", gl),
                ("Investigation tier on Terra instead of Sol", terra("DZ")),
                ("No prompt caching", self.case_cost("DZ", "Std", no_cache=True))]


def fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"


def quota_table(d: dict) -> list[str]:
    out = ["| Contract | Environment | Planned, M tokens | Quota, M tokens | Starting tokens a minute | Forecast-equivalent € | Worst case at the dearest alias € | In-flight overrun, tokens (€ at the dearest rate) |",
           "|---|---|---|---|---|---|---|---|"]
    for r in d["quotas"]:
        daily = f" ({r['daily'] / 1e6:,.1f} M a day)" if r["daily"] else ""
        out.append(f"| `{r['contract']}` | {r['env'].upper()} | {r['planned_tokens'] / 1e6:,.1f} | {r['quota_tokens'] / 1e6:,.0f}{daily} | "
                   f"{r['tpm'] / 1e3:,.0f} K | €{fmt(r['cap_eur'])} | €{fmt(r['worst_eur'])} | {r['overrun_tokens'] / 1e3:,.0f} K (€{r['overrun_eur']:.2f}) |")
    for e in ENVIRONMENTS:
        rows = [r for r in d["quotas"] if r["env"] == e]
        if not rows:
            continue
        out.append(f"| **All contracts** | **{e.upper()}** | **{sum(r['planned_tokens'] for r in rows) / 1e6:,.1f}** | "
                   f"**{sum(r['quota_tokens'] for r in rows) / 1e6:,.0f}** | | **€{fmt(sum(r['cap_eur'] for r in rows))}** | "
                   f"**€{fmt(sum(r['worst_eur'] for r in rows))}** | |")
    return out


ALL_ALIASES = {"triage", "reason", "judge-eu", "judge-pub", "embed", "batch"}


def expected_contracts() -> dict[str, dict]:
    """What design 04 section 4.3 must say about each contract: its aliases, the pools of its data class and whether
    it has no PROD product."""
    return {c: dict(aliases=CONTRACT_ALIASES[c], pools=CONTRACT_POOLS[c], noprod=(c in NO_PROD_CONTRACTS)) for c in CONTRACT_ALIASES}


def doc_contracts(text: str) -> dict[str, dict]:
    """The access-contract table of design 04 section 4.3: per contract the aliases it lists (and any bare word in
    that cell the model does not know), the pools of its data class, and whether it says 'no PROD product'."""
    m = re.search(r"### 4\.3 The access contracts(.*?)(?=\n#{2,4} |\Z)", text, re.S)
    table: dict[str, dict] = {}
    if not m:
        return table
    known = r"\b(" + "|".join(sorted(ALL_ALIASES)) + r")\b"
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"`[a-z-]+`", cells[0]):
            bare = [t for t in (x.strip() for x in cells[3].split(",")) if re.fullmatch(r"[a-z][a-z-]*", t)]
            table[cells[0].strip("`")] = dict(aliases=set(re.findall(known, cells[3])),
                                              unknown=sorted(t for t in bare if t not in ALL_ALIASES),
                                              pools=set(re.findall(r"`(acia-[a-z-]+)`", cells[2])),
                                              noprod="no prod product" in cells[4].lower())
    return table


def check_contracts(text: str, expected: dict[str, dict] | None = None) -> list[str]:
    """Design 04 section 4.3 and the model must name the same contracts with the same aliases and pools, and agree on
    which contracts have no PROD product."""
    expected = expected_contracts() if expected is None else expected
    got = doc_contracts(text)
    if not got:
        return ["04 section 4.3: the access-contract table was not found"]
    errs = []
    for c, want in expected.items():
        if c not in got:
            errs.append(f"04 section 4.3: the model's contract `{c}` is not in the table")
            continue
        have = got[c]
        if have["aliases"] != want["aliases"]:
            errs.append(f"04 section 4.3: contract `{c}` lists aliases {sorted(have['aliases'])} but the model prices {sorted(want['aliases'])}")
        if have["unknown"]:
            errs.append(f"04 section 4.3: contract `{c}` lists {have['unknown']}, which the model does not know as an alias")
        if have["pools"] != want["pools"]:
            errs.append(f"04 section 4.3: contract `{c}` reaches pools {sorted(have['pools'])} but the model's data class gives {sorted(want['pools'])}")
        if have["noprod"] != want["noprod"]:
            errs.append(f"04 section 4.3: contract `{c}` {'says' if have['noprod'] else 'does not say'} 'no PROD product' "
                        f"but the model {'has' if not want['noprod'] else 'has no'} PROD work for it")
    for c in got:
        if c not in expected:
            errs.append(f"04 section 4.3: contract `{c}` is in the table but not in the model")
    return errs


def doc_profile(text: str) -> dict[str, int]:
    """Design 14 section 4, 'Phase and capability profiles': the first phase whose row names each environment."""
    m = re.search(r"### Phase and capability profiles(.*?)(?=\n#{2,4} |\Z)", text, re.S)
    first: dict[str, int] = {}
    if not m:
        return first
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"\d", cells[0]):
            for tok, env in (("DEV", "dev"), ("PROD", "prod"), ("TEST", "test"), ("Lab", "lab")):
                if re.search(rf"\b{tok}\b", cells[1]) and env not in first:
                    first[env] = int(cells[0])
    return first


def check_profile(text: str) -> list[str]:
    """The phase in which each environment first exists must be the one that the model prices (design 14 section 4)."""
    got = doc_profile(text)
    if not got:
        return ["14 section 4: the phase and capability profile table was not found"]
    errs = []
    for env, phase in FIRST_PHASE.items():
        if env not in got:
            errs.append(f"14 section 4: no phase row names the {env.upper()} environment, which the model creates in phase {phase}")
        elif got[env] != phase:
            errs.append(f"14 section 4: the {env.upper()} environment first exists in phase {got[env]}, the model prices it from phase {phase}")
    return errs


NUMWORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                       "sixteen seventeen eighteen nineteen twenty".split())}
COUNT_PHRASES = {"roles": r"(?:agent\s+)?roles", "identities": r"(?:hosted-agent\s+|agent\s+)?identities",
                 "groups": r"(?:trust\s+|contract\s+)?groups", "contracts": r"(?:access\s+)?contracts"}


def doc_roster(text05: str) -> list[tuple[str, str]]:
    """Design 05 section 2: one (agent, group) per row of the roster table; the Librarian has two rows."""
    m = re.search(r"## 2\. The roster(.*?)(?=\n## |\Z)", text05, re.S)
    rows: list[tuple[str, str]] = []
    if not m:
        return rows
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"\*\*[^*]+\*\*", cells[0]):
            rows.append((cells[0].strip("*").strip(), cells[1].strip("` ")))
    return rows


def doc_agents(text04: str) -> dict[str, set[str]]:
    """Design 04 section 4.3: per contract the agents of its second column (a note such as 'on T3 cases' is not an agent)."""
    m = re.search(r"### 4\.3 The access contracts(.*?)(?=\n#{2,4} |\Z)", text04, re.S)
    out: dict[str, set[str]] = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"`[a-z-]+`", cells[0]):
            toks = [t.strip() for t in cells[1].split(",")]
            out[cells[0].strip("`")] = {t for t in toks if t and not t.lower().startswith("on ")}
    return out


def check_roster(text04: str, text05: str) -> tuple[list[str], dict[str, int]]:
    """The roster of 05 section 2 and the Agents column of 04 section 4.3 must name the same agents under the same
    groups; the counts that follow from them (roles, identities, groups, contracts) are returned for check_counts."""
    roster, agents = doc_roster(text05), doc_agents(text04)
    if not roster:
        return ["05 section 2: the roster table was not found"], {}
    if not agents:
        return ["04 section 4.3: the access-contract table was not found"], {}
    errs: list[str] = []
    listed: dict[str, set[str]] = {}
    for contract, labels in agents.items():
        if not labels:
            errs.append(f"04 section 4.3: contract `{contract}` lists no agent")
        for lab in labels:
            listed.setdefault(lab, set()).add(re.sub(r"-(pub|eu)$", "", contract))
    for lab, grp in roster:
        if lab not in listed:
            errs.append(f"05 section 2: `{lab}` (group {grp}) is in no contract's Agents column of 04 section 4.3")
        elif listed[lab] != {grp}:
            errs.append(f"05 section 2: `{lab}` is in group {grp} but 04 section 4.3 lists it under {sorted(listed[lab])}")
    known = {lab for lab, _ in roster}
    for lab in sorted(set(listed) - known):
        errs.append(f"04 section 4.3: `{lab}` is listed for a contract but is not in the roster of 05 section 2")
    counts = dict(roles=len({re.sub(r"\s*\(.*\)$", "", lab) for lab, _ in roster}), identities=len(roster),
                  groups=len({g for _, g in roster}), contracts=len(agents))
    return errs, counts


def check_counts(docs: dict[str, str], counts: dict[str, int]) -> list[str]:
    """Every document that states how many agent roles, identities, groups or contracts there are must state the
    number that the tables give. Numbers below ten are other things (the crew of three, the two contracts of examine);
    'the other thirteen identities' is the identities of the reasoning project, two fewer."""
    tok = "|".join(list(NUMWORDS) + [r"\d+"])
    errs: list[str] = []
    for name, text in sorted(docs.items()):
        for what, tail in COUNT_PHRASES.items():
            for m in re.finditer(rf"\b({tok})[*_]{{0,2}}\s+{tail}\b", text, re.I):
                t = m.group(1).lower()
                n = int(t) if t.isdigit() else NUMWORDS[t]
                if n < 10:
                    continue
                if what == "identities" and n == counts["identities"] - 2 and "other" in text[max(0, m.start() - 12):m.start()].lower():
                    continue
                if n != counts[what]:
                    errs.append(f"{name}: says '{m.group(0)}' but the tables give {counts[what]} {what}")
    return errs


def doc_pipeline_phases(text11: str) -> dict[str, int]:
    """Design 11 section 3, 'The pipelines read the phase profile': the first phase named for each environment in the
    sentence 'DEV in phases 0 and 1; DEV, then PROD in shadow, from phase 2; DEV, TEST and PROD from phase 3 ...'."""
    m = re.search(r"exists in the profile\*{0,2}:\s*(.*?);\s*never the Lab", text11, re.S)
    first: dict[str, int] = {}
    if not m:
        return first
    for clause in m.group(1).split(";"):
        n = re.search(r"(?:from|in) phases?\s+(\d)", clause)
        if not n:
            continue
        for tok, env in (("DEV", "dev"), ("TEST", "test"), ("PROD", "prod")):
            if re.search(rf"\b{tok}\b", clause):
                first[env] = min(first.get(env, int(n.group(1))), int(n.group(1)))
    return first


def check_pipeline_phases(text11: str) -> list[str]:
    """The pipelines paragraph of 11 section 3 must put each environment in the phase that 14 section 4 and the model do."""
    got = doc_pipeline_phases(text11)
    if not got:
        return ["11 section 3: the sentence 'A release deploys to the next environment that exists in the profile: ...; never the Lab' was not found"]
    errs = []
    for env in ("dev", "prod", "test"):
        if env not in got:
            errs.append(f"11 section 3: the pipelines paragraph does not say from which phase the {env.upper()} environment exists")
        elif got[env] != FIRST_PHASE[env]:
            errs.append(f"11 section 3: the pipelines paragraph creates {env.upper()} from phase {got[env]}, the model prices it from phase {FIRST_PHASE[env]}")
    return errs


def check_rows(scenario: str, rows: list[dict], expected: dict[str, set[str]] | None = None) -> list[str]:
    """Every declared contract has a quota in every environment where it has planned work, a quota never blocks the
    work it was derived from, and no quota exists for an environment that the scenario never creates or for a PROD
    product that a contract does not have (design 04 section 4.3, 14 section 4)."""
    expected = CONTRACT_ALIASES if expected is None else expected
    present = environments_present(SCENARIOS[scenario]) if scenario in SCENARIOS else list(ENVIRONMENTS)
    seen: dict[str, set[str]] = {}
    for r in rows:
        seen.setdefault(r["contract"], set()).add(r["env"])
    errs = []
    for c in expected:
        if c not in seen:
            errs.append(f"{scenario}: contract `{c}` has no quota row")
        elif "dev" not in seen[c]:
            errs.append(f"{scenario}: contract `{c}` has no DEV quota")
    for c in seen:
        if c not in expected:
            errs.append(f"{scenario}: a quota row for the unknown contract `{c}`")
    for r in rows:
        tag = f"{scenario}: the quota of {r['contract']}/{r['env']}"
        if r["env"] not in present:
            errs.append(f"{tag} is for an environment that this scenario never creates (design 14 section 4)")
        if r["env"] == "prod" and r["contract"] in NO_PROD_CONTRACTS:
            errs.append(f"{tag} is a PROD product for a contract that has none (design 04 section 4.3)")
        if r["quota_tokens"] < 1.2 * r["planned_tokens"]:
            errs.append(f"{tag} would block planned work")
        if r["worst_eur"] + 1e-9 < r["cap_eur"]:
            errs.append(f"{tag} has a worst case below its forecast-equivalent cap")
        if r["tpm"] <= 0 or r["overrun_tokens"] <= 0:
            errs.append(f"{tag} has no tokens-per-minute limit or overrun bound")
    return errs


def validate(model: Model, doc04: str | None = None, doc14: str | None = None, docs: dict[str, str] | None = None) -> list[str]:
    """A quota that blocks planned work, a contract without a row, an environment the phase profile does not create,
    or a summed cap far above the plan is a defect; so is a roster, a count or a pipelines paragraph that disagrees
    with the tables (design 04 section 4.3, 05 section 2, 11 section 3, 14 section 4)."""
    errs = []
    for n in SCENARIOS:
        d = model.scenario(n)
        errs.extend(check_rows(n, d["quotas"]))
        if d["cap_eur"] > QUOTA_CAP_LIMIT * d["plan_eur"]:
            errs.append(f"{n}: the summed forecast-equivalent cap {d['cap_eur']:.0f} exceeds {QUOTA_CAP_LIMIT} x the plan {d['plan_eur']:.0f}")
        prod_work = {r["contract"] for r in d["quotas"] if r["env"] == "prod" and r["has_work"]}
        if prod_work & NO_PROD_CONTRACTS:
            errs.append(f"{n}: planned PROD work for {sorted(prod_work & NO_PROD_CONTRACTS)}, which design 04 gives no PROD product")
        if n != "Pilot" and (set(CONTRACT_ALIASES) - NO_PROD_CONTRACTS) - prod_work:
            errs.append(f"{n}: no planned PROD work for {sorted((set(CONTRACT_ALIASES) - NO_PROD_CONTRACTS) - prod_work)}, which design 04 gives a PROD product")
    if doc04 is not None:
        errs.extend(check_contracts(doc04))
    if doc14 is not None:
        errs.extend(check_profile(doc14))
    if docs is not None:
        roster_errs, counts = check_roster(docs.get("04-landing-zone-and-citadel.md", ""), docs.get("05-agents-and-orchestration.md", ""))
        errs.extend(roster_errs)
        if counts:
            errs.extend(check_counts(docs, counts))
        errs.extend(check_pipeline_phases(docs.get("11-delivery-and-operations.md", "")))
    return errs


def selftest(model: Model) -> int:
    """Negative fixtures: each defect must be reported, and the clean input must pass."""
    head = "### 4.3 The access contracts\n\n| Contract | Agents | Data class · pools | Aliases | Quota | Safety |\n|---|---|---|---|---|---|\n"
    exp = expected_contracts()

    def row(c: str) -> str:
        pools = ", ".join(f"`{p}`" for p in sorted(exp[c]["pools"]))
        return (f"| `{c}` | agent | class · {pools} | {', '.join(sorted(exp[c]['aliases']))} | "
                f"12 §2{'; no PROD product' if exp[c]['noprod'] else ''} | safe |")

    rows = [row(c) for c in exp]
    clean = head + "\n".join(rows) + "\n\n### 4.4 next\n"
    first = next(iter(CONTRACT_ALIASES))
    study_row = rows[0]
    forge_row = row("forge")
    doc_cases = {
        "a contract missing from the table": head + "\n".join(rows[1:]) + "\n",
        "an extra contract in the table": clean.replace("### 4.4", "| `phantom` | a | b | reason | 12 §2 | x |\n\n### 4.4"),
        "an alias that the model does not price": clean.replace(study_row, study_row.replace(study_row.split("|")[4], " reason, judge-pub, embed, batch, triage ")),
        "an alias that the model does not know": clean.replace(study_row, study_row.replace(study_row.split("|")[4], study_row.split("|")[4].rstrip() + ", priority ")),
        "a contract that reaches another pool": clean.replace(study_row, study_row.replace("`acia-flex`", "`acia-eu`")),
        "a PROD product for a contract that has none": clean.replace(forge_row, forge_row.replace("; no PROD product", "")),
        "no table at all": "# nothing here\n",
    }
    team = model.scenario("Team")["quotas"]
    pilot = model.scenario("Pilot")["quotas"]
    row_cases = {
        "a contract without any row": ("Team", [r for r in team if r["contract"] != first]),
        "a contract without a DEV row": ("Team", [r for r in team if not (r["contract"] == first and r["env"] == "dev")]),
        "a quota that blocks planned work": ("Team", [dict(team[0], quota_tokens=team[0]["planned_tokens"])] + team[1:]),
        "a worst case below the forecast": ("Team", [dict(team[0], worst_eur=0.0)] + team[1:]),
        "a row for an unknown contract": ("Team", team + [dict(team[0], contract="phantom")]),
        "a TEST quota at Pilot scale, where no TEST account exists": ("Pilot", pilot + [dict(pilot[0], env="test")]),
        "a PROD quota for a contract that has no PROD product": ("Team", team + [dict(team[0], contract="forge", env="prod")]),
    }
    profile_head = "### Phase and capability profiles\n\n| Phase | Environments that exist | x |\n|---|---|---|\n"
    profile = profile_head + "| 0 | DEV | x |\n| 1 | DEV | x |\n| 2 | DEV, PROD (shadow) | x |\n| 3 | + TEST (Team scale) | x |\n| 4 | + the Lab account | x |\n"
    profile_cases = {
        "TEST created a phase early": profile.replace("| 2 | DEV, PROD (shadow) |", "| 2 | DEV, PROD, TEST |"),
        "PROD missing from the profile": profile.replace("DEV, PROD (shadow)", "DEV"),
        "no profile table at all": "# nothing here\n",
    }
    ok = not check_contracts(clean) and not check_rows("Team", team) and not check_rows("Pilot", pilot) and not check_profile(profile)
    print(f"clean fixtures: {'pass' if ok else 'FAIL'}")
    for label, text in doc_cases.items():
        found = bool(check_contracts(text))
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")
    for label, (scen, rws) in row_cases.items():
        found = bool(check_rows(scen, rws))
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")
    for label, text in profile_cases.items():
        found = bool(check_profile(text))
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")

    roster_doc = ("## 2. The roster\n\n| Agent | Group | Alias |\n|---|---|---|\n| **Scholar** | study | x |\n| **Librarian (Atlas)** | curate | x |\n"
                  "| **Librarian (lessons)** | govern | x |\n| **Auditor** | govern | x |\n| **Examiner** | examine | x |\n\n## 3. next\n")
    agents_head = "### 4.3 The access contracts\n\n| Contract | Agents | Data class | Aliases | Quota | Safety |\n|---|---|---|---|---|---|\n"
    agents_rows = ["| `study` | Scholar | public | reason | q | s |", "| `curate` | Librarian (Atlas) | public | reason | q | s |",
                   "| `govern` | Auditor, Librarian (lessons) | eu | reason | q | s |", "| `examine-pub` | Examiner, on synthetic estates | public | reason | q | s |",
                   "| `examine-eu` | Examiner, on T3 cases | eu | reason | q | s |"]
    agents_doc = agents_head + "\n".join(agents_rows) + "\n\n### 4.4 next\n"
    roster_cases = {
        "an agent that 04 lists under another group": agents_doc.replace("Auditor, Librarian (lessons)", "Librarian (lessons)").replace("| Scholar |", "| Scholar, Auditor |"),
        "an agent missing from the Agents column": agents_doc.replace("| Scholar |", "| |"),
        "an agent in 04 that the roster does not know": agents_doc.replace("| Scholar |", "| Scholar, Phantom |"),
    }
    base_errs, counts = check_roster(agents_doc, roster_doc)
    ok &= not base_errs and counts == dict(roles=4, identities=5, groups=4, contracts=5)
    print(f"clean roster fixtures: {'pass' if not base_errs and counts else 'FAIL'}")
    for label, text04 in roster_cases.items():
        found = bool(check_roster(text04, roster_doc)[0])
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")
    found = bool(check_roster(agents_doc, "# nothing here\n")[0])
    ok &= found
    print(f"  {'caught' if found else 'MISSED'}: no roster table at all")
    big = dict(roles=14, identities=15, groups=11, contracts=12)
    count_cases = {
        "prose that says thirteen roles": "We have thirteen roles.",
        "prose that says 16 identities": "all 16 identities are listed",
        "prose that says twelve groups": "in twelve groups",
        "prose that says fourteen contracts": "the fourteen contracts",
        "prose that bolds a wrong number": "Fourteen roles and **sixteen** identities (the Librarian is deployed twice)",
    }
    clean_count = "Fourteen agent roles, fifteen hosted-agent identities, eleven groups, twelve contracts, the other thirteen identities, three roles in the crew."
    count_ok = not check_counts({"a.md": clean_count}, big)
    ok &= count_ok
    print(f"clean count fixtures: {'pass' if count_ok else 'FAIL'}")
    for label, text in count_cases.items():
        found = bool(check_counts({"a.md": text}, big))
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")
    pipe = "**A release deploys to the next environment that exists in the profile**: DEV in phases 0 and 1; DEV, then PROD in shadow, from phase 2; DEV, TEST and PROD from phase 3 at Team scale; never the Lab, where experiments run."
    pipe_cases = {
        "TEST created in phase 2 by the pipelines paragraph": pipe.replace("DEV, TEST and PROD from phase 3", "DEV, TEST and PROD from phase 2"),
        "PROD created in phase 3 by the pipelines paragraph": pipe.replace("DEV, then PROD in shadow, from phase 2", "DEV, then DEV in shadow, from phase 2"),
        "no pipelines sentence at all": "# nothing here\n",
    }
    pipe_ok = not check_pipeline_phases(pipe)
    ok &= pipe_ok
    print(f"clean pipelines fixture: {'pass' if pipe_ok else 'FAIL'}")
    for label, text in pipe_cases.items():
        found = bool(check_pipeline_phases(text))
        ok &= found
        print(f"  {'caught' if found else 'MISSED'}: {label}")
    return 0 if ok else 1


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
               "Private Foundry accounts, one per environment, each with its own AI Search, Cosmos DB and Storage: " +
               ", ".join(f"{k} {v['accounts']}" for k, v in SCENARIOS.items()) +
               " (Pilot: development and production; Team and Enterprise add test and the Lab). They are created in the phase that needs them, "
               "except the AI Search services, which are created on day zero.")
    out.append("")
    out.append("**The inventory behind the floor** (design [04 §7](04-landing-zone-and-citadel.md#7-the-foundry-layout), [07 §6.1](07-security-architecture.md#61-secrets)):")
    out.append("")
    out.append("| Scenario | Foundry accounts | AI Search units | Spine environments | Chain environments | Key Vaults | Private endpoints |")
    out.append("|---|---|---|---|---|---|---|")
    for d in detail:
        i = d["inventory"]
        out.append(f"| {d['name']} | {i['accounts']} | {i['search_units']} | {i['envs']} | {i['chain_envs']} | {i['vaults']} | {i['pe']} |")
    out.append("")
    out.append(f"A spine environment holds the Durable Functions app, its storage and one secrets vault; a chain environment adds the {SIGNING_PARTIES} signing parties' vaults "
               f"(Approval, Policy, broker, runner, Verifier, Audit Writer) and the queue storage account `stchain`; one more vault holds the pipeline's signing key. Endpoints: {PE_PER_ACCOUNT} per Foundry account, "
               f"one per vault, {PE_PER_SPINE_ENV} per spine environment, {PE_PER_CHAIN_ENV} per chain environment and {PE_BASE} shared.")
    out.append("")
    shares = []
    for d in detail:
        g, t = d["groups"], d["total"]
        fixed = sum(v for k, v in g.items() if k not in ("Tokens", "Compute"))
        shares.append(f"{d['name']}: tokens {100 * g['Tokens'] / t:.0f} %, compute {100 * g['Compute'] / t:.0f} %, fixed and platform {100 * fixed / t:.0f} %")
    out.append("**Shares of the total (shared hub):** " + "; ".join(shares) + ".")
    out.append("")
    out.append("**The idle floor by phase** (design [14 §4](14-next-phases.md#4-phases); monthly euros with nothing running: Search, endpoints, Key Vault and Resource Manager Defender, "
               "the registry and, from phase 2, the spine's always-ready instance). The AI Search services are created on day zero, so a phase pays for the ones whose account does not exist yet:")
    out.append("")
    out.append("| Phase | Accounts that exist (Pilot / Team / Enterprise) | Idle floor € (Pilot / Team / Enterprise) | Of which Search reserved ahead of its account, € |")
    out.append("|---|---|---|---|")
    floors = {n: model.phase_floor(n) for n in SCENARIOS}
    for idx in range(len(floors["Pilot"])):
        rows = [floors[n][idx] for n in SCENARIOS]
        out.append(f"| {rows[0]['phase']} | " + " / ".join(str(len(r["envs"])) for r in rows) + " | "
                   + " / ".join(f"{fmt(r['floor'])}" for r in rows) + " | " + " / ".join(f"{fmt(r['early_eur'])}" for r in rows) + " |")
    out.append("")
    out.append("**The gate plan** (design [10 §4](10-test-and-evaluation.md#the-statistical-protocol): decoys for G3, comparison cases for G4, each run `r` times; the baselines are frozen and reused, so only the candidate runs; "
               "G5 is judged on the same runs, which the 30 % judge work covers):")
    out.append("")
    out.append("| Scenario | Gated domain-releases a month | Decoys | Comparison cases | Runs a case | Case-runs a month | Gate tokens € | Reviewer hours a month |")
    out.append("|---|---|---|---|---|---|---|---|")
    for d in detail:
        p, gt = d["params"], d["gate"]
        out.append(f"| {d['name']} | {p['gate_releases']} | {p['gate_decoys']} | {p['gate_cases']} | {p['gate_repeats']} | {gt['runs']:,.0f} | "
                   f"€{fmt(gt['eur'])} | {gt['review_hours']:.0f} |")
    out.append("")
    out.append("Pilot gates one narrow domain in shadow: its claim narrows instead of its statistics thinning. Reviewer hours are a person reading the failed critical cases and a fifth of the passed ones and "
               f"labelling the judges' sample, {GATE_REVIEW_HOURS:.0f} hours per gated domain-release (a seed).")
    out.append("")
    out.append("**Evaluation against production** (everything that runs the exams, the gates, the attacks, the forger and method learning, including the hosted-agent, sandbox, function and screening time that "
               "carry them, against the same lines for the production cases):")
    out.append("")
    out.append("| Scenario | Evaluation € | Production cases € | Evaluation as a multiple of production cases | Evaluation as a share of the total |")
    out.append("|---|---|---|---|---|")
    for d in detail:
        out.append(f"| {d['name']} | €{fmt(d['eval_eur'])} | €{fmt(d['cases_eur'])} | {d['eval_eur'] / d['cases_eur']:.1f} x | {100 * d['eval_eur'] / d['total']:.0f} % |")
    out.append("")
    out.append("**Hosted-agent sessions of the evaluation case-runs** (lever 17 of section 5: evaluate on jobs that run the same image), of which the idle tail, which is billed here on the conservative reading: "
               + "; ".join(f"{d['name']}: €{fmt(d['eval_sessions_eur'])}, of which €{fmt(d['eval_idle_eur'])}" for d in detail) + ".")
    out.append("")
    out.append("**Contract quotas next to the plan** (token quotas at " + f"{QUOTA_HEADROOM} x the planned tokens). The *forecast-equivalent* euros price the quota at the contract's own blended price; "
               "the *worst case* prices it at the dearest rate of the dearest alias the contract lists, and neither is a hard cap: the spine's atomic euro reservation is the budget that holds, "
               "and the hub's token limit is a second, coarser layer with a bounded overrun (section 6): "
               + "; ".join(f"{d['name']}: forecast-equivalent €{fmt(d['cap_eur'])}, worst case €{fmt(d['worst_eur'])}, token plan €{fmt(d['plan_eur'])}" for d in detail) + ".")
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
    out.append("**One case, on the strongest tier, by role** (EU Data Zone, marginal tokens only; a **warm-cache scenario**, not a measured saving: each role's session writes its static prefix once, "
               "bills it at the write price and reads it on later calls):")
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
    out.append("**Sensitivity of the monthly total** (change against the table above, shared hub, one assumption at a time):")
    out.append("")
    out.append("| Assumption that moves | " + " | ".join(SCENARIOS) + " |")
    out.append("|---|" + "---|" * len(SCENARIOS))
    for lab, deltas in model.monthly_sensitivities():
        out.append(f"| {lab} | " + " | ".join(f"{'+' if v >= 0 else '−'}€{fmt(abs(v))}" for v in deltas.values()) + " |")
    out.append("")
    out.append(f"**With labour: the all-in break-even** (share of monitored spend; labour at €{LABOUR_RATE_EUR:.0f} an hour is a stated seed, not a measurement; the gate review hours above are part of it; the 40-hour row is the Pilot-scale operating budget in [11 §7.2](11-delivery-and-operations.md#the-minimum-viable-profile-and-the-operating-budget)):")
    out.append("")
    out.append("| Labour a month | " + " | ".join(SCENARIOS) + " |")
    out.append("|---|" + "---|" * len(SCENARIOS))
    out.append("| none (cloud only) | " + " | ".join(f"{d['breakeven_pct']:.2f} %" for d in detail) + " |")
    for h in LABOUR_HOURS:
        out.append(f"| {h} h (€{h * LABOUR_RATE_EUR:,.0f}) | "
                   + " | ".join(f"{100.0 * (d['total'] + h * LABOUR_RATE_EUR) / d['params']['spend']:.2f} %" for d in detail) + " |")
    out.append("")
    team = next(d for d in detail if d["name"] == "Team")
    out.append("**Contract quotas at Team scale: every contract of [04 §4.3](04-landing-zone-and-citadel.md#43-the-access-contracts) in every environment where it has planned work.** "
               f"A quota is the planned tokens times {QUOTA_HEADROOM}, rounded up to a whole million; TEST and DEV carry at least {ENV_FLOOR['test']:.0%} and {ENV_FLOOR['dev']:.0%} of production's plan, "
               "or their own planned work where that is larger (exams, gates and attacks run in TEST on synthetic data, so TEST and DEV products reach the public pools). "
               "Pilot has no TEST account, so there DEV carries the exams, the gates and the attacks and its quotas are sized for them. "
               "The starting tokens a minute is the contract's peak concurrency times its largest call times two calls a minute; the in-flight overrun is the concurrency times the largest call, priced at the dearest rate. "
               "The tokens a minute are what the hub is configured to allow, not what the subscription is granted: Foundry quota follows the subscription's tier (Free and Tiers 1 to 6) and more is requested through the quota request form "
               "([Learn](https://learn.microsoft.com/azure/foundry/openai/quotas-limits)); the day-zero request of [14 §5](14-next-phases.md#5-pre-flight-checklist-day-zero) sizes it (assumption 7). "
               "`python tools/cost-model.py --quotas Pilot` (or `Enterprise`) prints the others, and `--check` fails if the table of 04 §4.3 disagrees with the model on a contract, its aliases, its pools or whether it has a PROD product, "
               "if the phase profile of 14 §4 creates an environment in another phase than the one priced here, or if a quota exists for an environment that a scenario never creates:")
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
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    prices = Prices(SNAP)
    model = Model(prices)
    if args.self_test:
        return selftest(model)
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
            doc04 = path.parent / "04-landing-zone-and-citadel.md"
            doc14 = path.parent / "14-next-phases.md"
            docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(path.parent.glob("*.md"))}
            errs = validate(model, doc04.read_text(encoding="utf-8") if doc04.exists() else "",
                            doc14.read_text(encoding="utf-8") if doc14.exists() else "", docs)
            for e in errs:
                print(f"{path}: {e}", file=sys.stderr)
            if m.group(0) != block:
                print(f"{path}: generated block is stale; run tools/cost-model.py --update-doc {path}", file=sys.stderr)
                return 1
            if errs:
                return 1
            print(f"{path}: cost block is current; quotas consistent with the plan, with the contracts and agents of 04 section 4.3, "
                  f"with the roster and the counts of 05 section 2, with the pipelines of 11 section 3 and with the phase profile of 14 section 4")
            return 0
        path.write_text(text[: m.start()] + block + text[m.end():], encoding="utf-8")
        print(f"updated {path}")
        return 0
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
