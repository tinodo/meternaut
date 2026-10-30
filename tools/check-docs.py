#!/usr/bin/env python3
"""Docs lint for the Azure Cost in Action ideation package.

Standard library only (no packages to install). Run from anywhere:

    python tools/check-docs.py            # human-readable report, exit code 1 on any ERROR
    python tools/check-docs.py --strict   # WARNINGs also fail

Checks (and why they exist - each one came from a review finding):
  1. Relative links and heading anchors resolve (docs/_archive is skipped).
  2. The opportunity catalog has unique IDs, and its row count matches the README claim.
  3. Classification lint (06 section 2): the declared Rev/Ceil of every catalog row must not break
     the rules - R3 / R3-Data never at L3-L5, transactions never above L2, no hybrid classes such
     as "R0/R1", R3-D is the only abbreviation of R3-Data, and rows that touch observability data
     are R3-D (WARN: needs a human look).
  4. Counts quoted in the README (threats, invariants, spikes, risks, decisions, assumptions)
     match what the documents actually contain.
  5. Mermaid labels: unquoted square-bracket labels must not contain ( ) " { } ;
  6. Stale phrases that earlier reviews removed must not come back.
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {".git", "_archive", "node_modules"}
HISTORY_DIRS = {"reviews"}  # raw reviewer text and dispositions quote old wording on purpose

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def md_files(include_history=True):
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        if not include_history and any(part in HISTORY_DIRS for part in rel(dp).split("/")):
            continue
        for f in fn:
            if f.endswith(".md"):
                out.append(os.path.join(dp, f))
    return out


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- 1. links and anchors
def slug(h):
    h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h)
    h = h.replace("`", "").replace("*", "").strip().lower()
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


_anchor_cache = {}


def anchors(path):
    if path in _anchor_cache:
        return _anchor_cache[path]
    seen, found, in_code = {}, set(), False
    for line in read(path).split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(2))
            if s in seen:
                seen[s] += 1
                found.add(f"{s}-{seen[s]}")
            else:
                seen[s] = 0
                found.add(s)
    _anchor_cache[path] = found
    return found


def check_links():
    link_re = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    total = 0
    for p in md_files():
        in_code = False
        for i, line in enumerate(read(p).split("\n"), 1):
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for m in link_re.finditer(line):
                t = m.group(1)
                if t.startswith(("http://", "https://", "mailto:")):
                    continue
                total += 1
                frag = None
                if "#" in t:
                    t, frag = t.split("#", 1)
                target = p if t == "" else os.path.normpath(os.path.join(os.path.dirname(p), t))
                if not os.path.exists(target):
                    err(f"{rel(p)}:{i} link target missing: {m.group(1)}")
                    continue
                if frag and target.endswith(".md") and frag.lower() not in anchors(target):
                    err(f"{rel(p)}:{i} anchor missing: {m.group(1)}")
    return total


# ---------------------------------------------------------------- 2/3. catalog
CATALOG = os.path.join(ROOT, "docs", "ideation", "02-opportunity-catalog.md")
ROW_RE = re.compile(r"^\| ([A-Z]+-\d+)\b")
TRANSACTION_WORDS = re.compile(r"\b(cancel|purchase|exchange|renew|reservation|savings plan|commitment)\b", re.I)
OBSERVABILITY_WORDS = re.compile(
    r"\b(ingest\w*|diagnostic|log|logs|logging|metric|metrics|telemetry|retention|sampling|flow logs?|"
    r"capture|change feed|syslog|counters?|trace|traces|audit)\b",
    re.I,
)


def catalog_rows():
    text = read(CATALOG).split("\n")
    start = next(i for i, l in enumerate(text) if l.startswith("## 1. IDLE"))
    end = next(i for i, l in enumerate(text) if l.startswith("## Selection and status"))
    rows = []
    for ln in range(start, end):
        line = text[ln]
        if ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6:
                rows.append((ln + 1, cells))
    return rows


def check_catalog():
    rows = catalog_rows()
    ids = [re.match(r"[A-Z]+-\d+", c[0]).group(0) for _, c in rows]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        err(f"catalog: duplicate IDs {dup}")
    readme = read(os.path.join(ROOT, "README.md"))
    m = re.search(r"(\d+) ideas in 17 families", readme)
    if m and int(m.group(1)) != len(ids):
        err(f"README claims {m.group(1)} catalog ideas but the catalog has {len(ids)} rows")
    catalog_text = read(CATALOG)
    if "## At a glance" in catalog_text:
        block = catalog_text.split("## At a glance")[1].split("\n## ")[0]
        per_family = {}
        for cid in ids:
            fam = cid.split("-")[0]
            per_family[fam] = per_family.get(fam, 0) + 1
        seen = set()
        for fm in re.finditer(r"^\| \*\*([A-Z]+)\*\* \| (\d+) \|", block, re.M):
            seen.add(fm.group(1))
            if per_family.get(fm.group(1)) != int(fm.group(2)):
                err(f"catalog 'At a glance' says {fm.group(1)}={fm.group(2)} but the family has {per_family.get(fm.group(1))} rows")
        if seen != set(per_family):
            err(f"catalog 'At a glance' families {sorted(seen)} differ from the catalog's {sorted(per_family)}")
        tm = re.search(r"\*\*(\d+) ideas in 17 families\*\*", block)
        if tm and int(tm.group(1)) != len(ids):
            err(f"catalog 'At a glance' says {tm.group(1)} ideas but the catalog has {len(ids)} rows")
    for ln, c in rows:
        cid, opp, signal, action, rev, ceil = c[0], c[1], c[2], c[3], c[4], c[5]
        rev_key = re.sub(r"[^A-Za-z0-9\-/]", "", rev)
        ceil_levels = set(re.findall(r"L([0-5])", ceil))
        high = bool(ceil_levels & {"3", "4", "5"})
        text = f"{opp} {action}"
        if "/" in rev_key:
            err(f"{rel(CATALOG)}:{ln} {cid}: hybrid class '{rev}' (exactly one class per operation)")
        if rev_key in {"R3-D", "R3-Data", "R3"} and high and "cost-brake" not in ceil.lower():
            err(f"{rel(CATALOG)}:{ln} {cid}: {rev_key} must never be L3/L4/L5 (Ceil says '{ceil}')")
        if rev_key == "R3" and TRANSACTION_WORDS.search(text) and high:
            err(f"{rel(CATALOG)}:{ln} {cid}: a transaction must never be above L2 (Ceil says '{ceil}')")
        if TRANSACTION_WORDS.search(action) and re.search(r"\b(cancel|purchase|exchange|renew)\b", action, re.I):
            if high:
                err(f"{rel(CATALOG)}:{ln} {cid}: action '{action}' looks like a transaction but Ceil is '{ceil}'")
        if OBSERVABILITY_WORDS.search(text) and rev_key not in {"R3-D", "R3-Data", "R3", "\u2014", ""} and rev_key != "-":
            if re.search(r"\b(stop|disable|remove|reduce|narrow|drop|exclude|filter|lower|shorten|lifecycle|sampl)\w*", action, re.I):
                warn(f"{rel(CATALOG)}:{ln} {cid}: touches observability data and is '{rev_key}' - check it is not R3-Data: {opp[:70]}")
    return len(ids)


# ---------------------------------------------------------------- 4. counts
def count_in(path, pattern, flags=0):
    return len(re.findall(pattern, read(path), flags))


def check_counts():
    readme = read(os.path.join(ROOT, "README.md"))
    d08 = os.path.join(ROOT, "docs", "ideation", "08-trust-safety-and-guardrail-topics.md")
    d01 = os.path.join(ROOT, "docs", "plan", "01-assumptions-risks-decisions.md")
    d03 = os.path.join(ROOT, "docs", "plan", "03-capability-radar.md")
    threats = count_in(d08, r"^\| T\d+ \|", re.M)
    questions = count_in(d08, r"^- G\d+-\d+ ", re.M)
    text08 = read(d08)
    inv_block = text08.split("## 4. Candidate safety invariants")[1].split("## 5.")[0]
    invariants = len(re.findall(r"^\d+\. \*\*", inv_block, re.M))
    assumptions = count_in(d01, r"^\| A\d+ \|", re.M)
    risks = count_in(d01, r"^\| R\d+ \|", re.M)
    decisions = count_in(d01, r"^\| \*\*D\d+\*\*", re.M)
    spikes_all = set(re.findall(r"^\| \*\*(S\d+b?)\*\*", read(d03), re.M))
    deferred = set(re.findall(r"^\| \*\*(S\d+)\*\* \| [^|]*\u2014 \*\*(?:deferred|folded)", read(d03), re.M))
    active = len(spikes_all - deferred)

    def claim(label, actual, pattern):
        for m in re.finditer(pattern, readme):
            if int(m.group(1)) != actual:
                err(f"README says {m.group(0)!r} but the documents have {actual} {label}")

    claim("threats", threats, r"(\d+) threats")
    claim("guardrail questions", questions, r"(\d+) questions")
    claim("candidate invariants", invariants, r"(\d+) candidate invariants")
    claim("assumptions", assumptions, r"(\d+) assumptions")
    claim("risks", risks, r"(\d+) risks")
    claim("decisions", decisions, r"(\d+) decisions")
    claim("active spikes", active, r"(\d+) active feasibility spikes")
    return dict(threats=threats, questions=questions, invariants=invariants, assumptions=assumptions,
                risks=risks, decisions=decisions, spikes=active)


# ---------------------------------------------------------------- 5. mermaid
def check_mermaid():
    blocks = 0
    for p in md_files(include_history=False):
        lines = read(p).split("\n")
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("```mermaid"):
                j, body = i + 1, []
                while j < len(lines) and not lines[j].strip().startswith("```"):
                    body.append((j + 1, lines[j]))
                    j += 1
                blocks += 1
                first = next((b for b in body if b[1].strip()), (0, ""))[1].strip()
                if first.startswith(("flowchart", "graph")):
                    for ln, t in body[1:]:
                        for lab in re.findall(r"\[([^\]]*)\]", t):
                            if not lab.startswith('"') and re.search(r'[()"{};]', lab):
                                err(f"{rel(p)}:{ln} mermaid square label needs quotes or simpler text: [{lab}]")
                        for lab in re.findall(r"\{([^}]*)\}", t):
                            if re.search(r'[()"\[\];]', lab):
                                err(f"{rel(p)}:{ln} mermaid diamond label has special characters: {{{lab}}}")
                        for lab in re.findall(r"\|([^|]*)\|", t):
                            if re.search(r'[()"\[\]{};]', lab):
                                err(f"{rel(p)}:{ln} mermaid edge label has special characters: |{lab}|")
                i = j
            i += 1
    return blocks


# ---------------------------------------------------------------- 6. stale phrases and aliases
STALE = [
    (r"Everything has an undo window", "universal undo promise (round 1 R2)"),
    (r"Is anyone watching me\?\s*\*?\*?\s*No\.", "blanket 'nobody is watching' claim (round 1 G-14)"),
    (r"AI-generated \.", "card footer must read 'AI-composed - figures computed' (round 1)"),
    (r"Quarantine ladder: restrict, stop, snapshot", "silence-to-quarantine orphan flow (round 1 R3)"),
    (r"R0/R1", "hybrid reversibility class (round 1 G-10)"),
    (r"Release 1 is the first five rows", "Release 1 is five plays on the S0 skeleton (round 2 C-02)"),
    (r"\bno objection so far\b", "'no objection' is silence, not consent (round 2 A-05)"),
    (r"until further notice", "reservation exchange wording is outdated (round 2 fact-check)"),
    (r"brief reconnects", "P2S: Microsoft says to plan for downtime; 'TCP reconnects' is the ExpressRoute entry (round 2 fact-check)"),
    (r"documented inconsistently", "say 'unreconciled' (round 2 fact-check)"),
    (r"explicit, dated unmet need", "Easy Buttons is an additional theme, not a top-three need (round 2 fact-check)"),
    (r"\*\*S[0-8] — ", "slice IDs are SL0-SL8; S1-S22 are spikes (round 2 orchestrator finding)"),
]
ALLOW_STALE_IN = {
    "R0/R1": {"docs/ideation/02-opportunity-catalog.md", "docs/ideation/05-human-interaction-concepts.md",
              "docs/ideation/06-closed-loop-actions-and-autonomy.md", "docs/ideation/08-trust-safety-and-guardrail-topics.md",
              "CHANGELOG.md", "tools/check-docs.py"},
    "Quarantine ladder: restrict, stop, snapshot": {"CHANGELOG.md"},
    "until further notice": {"docs/research/01-azure-native-landscape.md", "docs/research/05-cost-traps-and-dark-spend.md",
                             "docs/ideation/02-opportunity-catalog.md", "CHANGELOG.md"},
    r"\bno objection so far\b": {"docs/ideation/06-closed-loop-actions-and-autonomy.md", "CHANGELOG.md"},
    "brief reconnects": {"docs/research/04-seed-example-facts.md", "CHANGELOG.md"},
    "documented inconsistently": {"CHANGELOG.md"},
    "explicit, dated unmet need": {"docs/research/03-finops-framework-and-evidence.md", "CHANGELOG.md"},
}


def check_stale():
    for p in md_files(include_history=False):
        r = rel(p)
        if r == "tools/check-docs.py":
            continue
        text = read(p)
        for pat, why in STALE:
            m = re.search(pat, text)
            if not m:
                continue
            allowed = ALLOW_STALE_IN.get(pat.replace("\\", ""), set()) | ALLOW_STALE_IN.get(pat, set())
            if r in allowed:
                continue
            line = text[: m.start()].count("\n") + 1
            err(f"{r}:{line} stale phrase {m.group(0)!r}: {why}")
    # the lint also protects the alias rule: R3-D may appear only in the catalog and (as a plain
    # abbreviation) where the catalog is quoted - never in other normative documents.
    alias_ok = {"docs/ideation/02-opportunity-catalog.md"}
    for p in md_files(include_history=False):
        r = rel(p)
        if r in alias_ok or r == "tools/check-docs.py" or r == "CHANGELOG.md":
            continue
        for i, line in enumerate(read(p).split("\n"), 1):
            if re.search(r"\bR3-D\b", line):
                err(f"{r}:{i} use the enum 'R3-Data' (R3-D is only a catalog column abbreviation)")


def main():
    strict = "--strict" in sys.argv
    links = check_links()
    rows = check_catalog()
    counts = check_counts()
    blocks = check_mermaid()
    check_stale()
    print(f"links checked: {links}; catalog rows: {rows}; mermaid blocks: {blocks}")
    print("counts:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors or (strict and warnings) else 0)


if __name__ == "__main__":
    main()
