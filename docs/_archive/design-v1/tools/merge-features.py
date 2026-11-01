#!/usr/bin/env python3
"""Merge the per-slice feature digests into one generated register. Standard library only.

Input : docs/design/research/features-01.md ... features-08.md (written by the triage agents)
Output: docs/design/research/feature-register.md (generated - never edit by hand)

The register lists every cluster once, grouped by disposition, and reports whether every row of the
attached list (lines 11-827) was triaged exactly once. Run: python tools/merge-features.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "docs" / "design" / "research"
OUT = RES / "feature-register.md"
SLICES = {1: (11, 112), 2: (113, 214), 3: (215, 316), 4: (317, 418),
          5: (419, 520), 6: (521, 622), 7: (623, 724), 8: (725, 827)}
CODES = {"A": "ADOPT", "AP": "ADOPT-PREVIEW", "E": "EVALUATE", "W": "WATCH", "N": "N/A"}
ORDER = ["ADOPT", "ADOPT-PREVIEW", "EVALUATE", "WATCH", "N/A", "UNSET"]
COMPONENTS = ("GW AGT FW MOD KNW TOOL ID SEC GOV OBS EVAL DATA COMP NET CHAN OPS COST LAB DEV").split()


def norm_disp(text: str) -> str:
    t = re.sub(r"[`*_]", "", text).strip().upper()
    t = t.replace("ADOPT (PREVIEW)", "ADOPT-PREVIEW").replace("ADOPT PREVIEW", "ADOPT-PREVIEW")
    if t in CODES:
        return CODES[t]
    for k in ("ADOPT-PREVIEW", "ADOPT", "EVALUATE", "WATCH", "N/A"):
        if t.startswith(k):
            return k
    m = re.match(r"(AP|A|E|W|N)\b", t)
    if m:
        return CODES[m.group(1)]
    return "UNSET"


def split_cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    key = "_head"
    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.*)$", line)
        if m:
            h = m.group(1).lower()
            if "cluster" in h:
                key = "clusters"
            elif "triage" in h:
                key = "rows"
            elif "finding" in h or "change the design" in h:
                key = "findings"
            elif "could not" in h or "verify" in h:
                key = "unverified"
            else:
                key = "_other:" + h
            out.setdefault(key, [])
            continue
        out.setdefault(key, []).append(line)
    return out


def parse_clusters(lines: list[str]) -> list[dict]:
    rows, header = [], None
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = split_cells(line)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))

        def col(*keys: str) -> str:
            for i, h in enumerate(header):
                if any(k in h for k in keys):
                    return cells[i]
            return ""

        rows.append({
            "id": re.sub(r"[`*]", "", col("id", "#")),
            "feature": col("feature", "name"),
            "status": col("status"),
            "what": col("what it does", "what"),
            "fit": col("fit"),
            "disp": norm_disp(col("disposition", "disp")),
            "why": col("why"),
            "notes": col("cost", "security", "note"),
            "sources": col("source"),
        })
    return rows


ROW = re.compile(r"^\s*(?:[-*|]\s*)?`?(\d{1,3})`?\s*[\u00b7|:]\s*(.*)$")


def parse_rows(lines: list[str]) -> dict[int, tuple[str, str, str]]:
    got: dict[int, tuple[str, str, str]] = {}
    for line in lines:
        m = ROW.match(line)
        if not m:
            continue
        n = int(m.group(1))
        body = m.group(2).replace("`", "").rstrip("| ")
        parts = [p.strip() for p in re.split(r"\s[\u00b7|]\s", body)]
        code, cluster, title = "", "-", m.group(2)
        for i, p in enumerate(parts):
            if p.upper() in CODES or p.upper() in CODES.values():
                code = p.upper()
                title = " / ".join(parts[:i])
                cluster = parts[i + 1] if i + 1 < len(parts) else "-"
                break
        got[n] = (title, norm_disp(code), cluster)
    return got


def first_url(text: str) -> str:
    m = re.search(r"https?://[^\s)\]>|]+", text)
    return m.group(0) if m else ""


def clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def main() -> int:
    clusters: list[dict] = []
    findings: dict[int, list[str]] = {}
    unverified: dict[int, list[str]] = {}
    coverage: dict[int, list[int]] = {}
    rowcodes: Counter = Counter()
    duplicates: list[int] = []
    seen_rows: set[int] = set()
    present = []
    for n, (lo, hi) in SLICES.items():
        p = RES / f"features-{n:02d}.md"
        if not p.exists():
            coverage[n] = list(range(lo, hi + 1))
            continue
        present.append(n)
        sec = sections(p.read_text(encoding="utf-8"))
        for c in parse_clusters(sec.get("clusters", [])):
            c["slice"] = n
            clusters.append(c)
        rows = parse_rows(sec.get("rows", []))
        for line_no, (_t, code, _c) in rows.items():
            if line_no in seen_rows:
                duplicates.append(line_no)
            seen_rows.add(line_no)
            rowcodes[code] += 1
        coverage[n] = [x for x in range(lo, hi + 1) if x not in rows]
        findings[n] = [l for l in sec.get("findings", []) if l.strip()]
        unverified[n] = [l for l in sec.get("unverified", []) if l.strip()]

    by = defaultdict(list)
    for c in clusters:
        by[c["disp"]].append(c)

    out = ["# Feature register (generated)", "",
           "> **Generated by `tools/merge-features.py` from the eight slice digests — do not edit by hand.** "
           "Each cluster links to its slice digest for the evidence.", "",
           f"Slices present: {', '.join(f'F{n}' for n in present) or 'none'} · clusters: {len(clusters)} · "
           f"rows triaged: {len(seen_rows)} of 817", "",
           "| Disposition | Clusters | Rows |", "|---|---|---|"]
    for d in ORDER:
        out.append(f"| {d} | {len(by.get(d, []))} | {rowcodes.get(d, 0)} |")
    out.append("")
    for d in ("ADOPT", "ADOPT-PREVIEW", "EVALUATE"):
        items = by.get(d, [])
        out += [f"## {d} ({len(items)})", "", "| Id | Feature | Status | Fit for our design | Notes |", "|---|---|---|---|---|"]
        for c in sorted(items, key=lambda x: (re.sub(r"[`*]", "", x["fit"]).split()[0] if x["fit"] else "~", x["id"])):
            out.append(f"| {c['id']} | {clip(c['feature'], 70)} | {clip(c['status'], 70)} | {clip(c['fit'], 260)} | {clip(c['notes'], 200)} |")
        out.append("")
    for d in ("WATCH", "UNSET"):
        items = by.get(d, [])
        if not items:
            continue
        out += [f"## {d} ({len(items)})", "", "| Id | Feature | Status |", "|---|---|---|"]
        for c in items:
            out.append(f"| {c['id']} | {clip(c['feature'], 80)} | {clip(c['status'], 60)} |")
        out.append("")
    out += ["## Findings that change the design, by slice", ""]
    for n in present:
        out += [f"### F{n}", ""] + findings.get(n, []) + [""]
    out += ["## Coverage check", ""]
    for n in SLICES:
        miss = coverage.get(n, [])
        out.append(f"- F{n}: {'complete' if not miss else 'missing ' + str(len(miss)) + ' rows: ' + ', '.join(map(str, miss[:40])) + (' ...' if len(miss) > 40 else '')}")
    if duplicates:
        out.append(f"- rows triaged more than once: {', '.join(map(str, sorted(set(duplicates))))}")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUT} - clusters {len(clusters)}, rows {len(seen_rows)}/817, slices {present}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
