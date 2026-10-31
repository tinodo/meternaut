#!/usr/bin/env python3
"""Documentation lint for Azure Cost in Action. Standard library only.

Checks
  1. Links and anchors in live documents resolve (GitHub heading-slug rules).
  2. Mermaid blocks: known diagram type, balanced quotes and brackets, quoted labels where
     needed, and no linear pipeline - a single chain, or one path through most nodes with no
     hub, even if closed into a ring (pictures must show loops, hubs, parallel work).
  3. SVG files are well-formed XML.
  4. Every live document is reachable from README.md (no orphans).
  5. Anchoring guard: the two findings that started the project may appear only in the exam
     documents - never as the foundation of the design (AGENTS.md rule 6).
  6. Bloat guard: no governance-paperwork vocabulary in the live documents (AGENTS.md rule 2).

Usage:  python tools/check-docs.py [--strict] [--self-test]
        --strict  treats warnings as errors (use before every commit)
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Documents in which the operator's original examples may legitimately appear.
ANCHOR_ALLOWLIST = {
    "docs/07-getting-smarter.md",
    "docs/research/exam-bank-cost-traps.md",
}
ANCHOR_PATTERNS = [
    r"\bP2S\b", r"point[- ]to[- ]site", r"\bvWAN\b", r"virtual wan", r"LAQueryLogs",
    r"seed[- ]example", r"release[- ]1\b", r"log analytics",
    r"never read\b", r"nobody (?:ever )?reads", r"read by nobody", r"scaled up long ago",
    r"idle gateway", r"shared gateway", r"unused logs", r"never queried",
]
BLOAT_PATTERNS = [
    (r"kill criteri", re.I), (r"risk register", re.I), (r"assumption register", re.I),
    (r"decision register", re.I), (r"technical spike", re.I), (r"threat catalog", re.I),
    (r"honest unknowns", re.I), (r"exit criteria", re.I), (r"assumptions? list", re.I),
    (r"R3-Data", 0), (r"\bK[1-7]\b", 0), (r"\bD(?:1[0-8]|[1-9])\b", 0),
]
MERMAID_TYPES = (
    "flowchart", "graph", "stateDiagram-v2", "stateDiagram", "sequenceDiagram", "classDiagram",
    "erDiagram", "gantt", "pie", "mindmap", "timeline", "journey", "quadrantChart", "gitGraph",
)

FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w-]*)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK = re.compile(r"!?\[(?:[^\]\\]|\\.)*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, path: Path, line: int, msg: str) -> None:
        self.errors.append(f"{rel(path)}:{line}: ERROR: {msg}")

    def warn(self, path: Path, line: int, msg: str) -> None:
        self.warnings.append(f"{rel(path)}:{line}: WARN: {msg}")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def slugify(heading: str) -> str:
    """GitHub's heading-to-anchor rule: lower-case, drop punctuation, spaces to hyphens."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def parse(text: str):
    """Return (prose_lines, fenced_blocks, headings). Line numbers are 1-based."""
    prose, blocks, headings = [], [], []
    in_fence, fence_mark, lang, buf, start = False, "", "", [], 0
    for n, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if m and not in_fence:
            in_fence, fence_mark, lang, buf, start = True, m.group(1)[:3], m.group(2), [], n
            continue
        if in_fence:
            if line.strip().startswith(fence_mark):
                blocks.append((lang, start, buf))
                in_fence = False
            else:
                buf.append(line)
            continue
        prose.append((n, line))
        h = HEADING.match(line)
        if h:
            headings.append((n, len(h.group(1)), h.group(2)))
    return prose, blocks, headings


def anchors_of(headings) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for _, _, title in headings:
        slug = slugify(title)
        k = seen.get(slug, 0)
        seen[slug] = k + 1
        out.add(slug if k == 0 else f"{slug}-{k}")
    return out


def live_files() -> list[Path]:
    files = [ROOT / n for n in ("README.md", "AGENTS.md", "CHANGELOG.md")]
    for p in sorted(DOCS.rglob("*.md")):
        parts = p.relative_to(DOCS).parts
        if parts[0] == "_archive":
            continue
        if parts[0] == "reviews" and p.name.startswith("raw-"):
            continue
        files.append(p)
    return [f for f in files if f.exists()]


def check_links(files, parsed, anchor_cache, rep: Report):
    graph: dict[Path, set[Path]] = {f: set() for f in files}
    for f in files:
        prose, _, _ = parsed[f]
        for n, line in prose:
            for m in LINK.finditer(INLINE_CODE.sub("", line)):
                target = m.group(1)
                if re.match(r"^(https?:|mailto:)", target, re.I):
                    continue
                path_part, _, frag = target.partition("#")
                dest = f if not path_part else (f.parent / unquote(path_part)).resolve()
                if not dest.exists():
                    rep.error(f, n, f"broken link target: {target}")
                    continue
                if dest.suffix.lower() == ".md" and dest in graph:
                    graph[f].add(dest)
                if frag and dest.suffix.lower() == ".md":
                    if dest not in anchor_cache:
                        _, _, hs = parse(dest.read_text(encoding="utf-8"))
                        anchor_cache[dest] = anchors_of(hs)
                    if unquote(frag).lower() not in anchor_cache[dest]:
                        rep.error(f, n, f"broken anchor: {target}")
    return graph


def check_orphans(files, graph, rep: Report):
    start = ROOT / "README.md"
    seen, todo = {start}, [start]
    while todo:
        for nxt in graph.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    for f in files:
        if f.parent == DOCS or f.parent.parent == DOCS and f.parent.name in ("research", "reviews"):
            if f not in seen:
                rep.error(f, 1, "orphan: not reachable from README.md")


def strip_labels(line: str) -> str:
    line = re.sub(r'"[^"]*"', '""', line)
    line = re.sub(r"\|[^|]*\|", "", line)
    for _ in range(3):
        line = re.sub(r"\[[^\[\]]*\]|\([^()]*\)|\{[^{}]*\}", "", line)
    return line


def mermaid_edges(lines):
    edges, nodes = set(), set()
    arrow = re.compile(r"\s*(?:<-->|<==>|-\.->|-\.-|-->|==>|---|--x|--o)\s*")
    skip = ("subgraph", "end", "classdef", "class ", "style ", "linkstyle", "direction", "%%", "click ")
    for raw in lines:
        s = raw.strip()
        if not s or s.lower().startswith(("flowchart", "graph") + skip):
            continue
        clean = strip_labels(s)
        both = "<-->" in clean or "<==>" in clean
        groups = [[x.strip() for x in p.split("&") if x.strip()] for p in arrow.split(clean)]
        for g in groups:
            nodes.update(re.findall(r"[A-Za-z_]\w*", " ".join(g)))
        for left, right in zip(groups, groups[1:]):
            for a in left:
                for b in right:
                    edges.add((a, b))
                    if both:
                        edges.add((b, a))
    return nodes, edges


def is_linear(nodes, edges) -> bool:
    if len(nodes) < 5 or len(edges) != len(nodes) - 1:
        return False
    out, inn = {}, {}
    for a, b in edges:
        out[a] = out.get(a, 0) + 1
        inn[b] = inn.get(b, 0) + 1
    if max(out.values(), default=0) > 1 or max(inn.values(), default=0) > 1:
        return False
    adj = {n: set() for n in nodes}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, todo = set(), [next(iter(nodes))]
    while todo:
        x = todo.pop()
        if x not in seen:
            seen.add(x)
            todo.extend(adj[x] - seen)
    return len(seen) == len(nodes)


def longest_path_nodes(nodes, edges) -> int:
    """Number of nodes on the longest simple directed path (graphs here are small)."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    best = 0

    def walk(n: str, seen: set[str]) -> None:
        nonlocal best
        best = max(best, len(seen))
        if best == len(nodes):
            return
        for m in adj.get(n, ()):
            if m not in seen:
                walk(m, seen | {m})

    for start in nodes:
        walk(start, {start})
        if best == len(nodes):
            break
    return best


def max_degree(nodes, edges) -> int:
    deg = {n: 0 for n in nodes}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return max(deg.values(), default=0)


def is_pipeline_in_disguise(nodes, edges) -> bool:
    """One path through at least 80% of the nodes and no hub: a chain, even if closed into a ring."""
    if len(nodes) < 6 or len(nodes) > 24:
        return False
    return longest_path_nodes(nodes, edges) >= 0.8 * len(nodes) and max_degree(nodes, edges) < 4


def check_mermaid(path: Path, blocks, rep: Report):
    for lang, start, lines in blocks:
        if lang != "mermaid":
            continue
        body = [ln for ln in lines if ln.strip()]
        if not body:
            rep.error(path, start, "empty mermaid block")
            continue
        head = body[0].strip()
        kind = next((t for t in MERMAID_TYPES if head.startswith(t)), None)
        if kind is None:
            rep.error(path, start, f"unknown mermaid diagram type: {head[:30]!r}")
            continue
        depth = 0
        for i, raw in enumerate(lines, 1):
            ln = start + i
            if raw.strip().startswith("%%"):
                continue
            if raw.count('"') % 2:
                rep.error(path, ln, "unbalanced double quotes in mermaid line")
            unq = re.sub(r'"[^"]*"', '""', raw)
            for a, b in ("[]", "()", "{}"):
                if unq.count(a) != unq.count(b):
                    rep.error(path, ln, f"unbalanced {a}{b} in mermaid line")
            if unq.count("|") % 2:
                rep.error(path, ln, "unbalanced | in mermaid edge label")
            if kind in ("flowchart", "graph"):
                for lab in re.findall(r"\w\s*(?:\[\[|\[\(|\(\(|\{\{|\[|\(|\{)([^\]\)\}\"]+)(?:\]\]|\)\]|\)\)|\}\}|\]|\)|\})", unq):
                    if re.search(r"[^A-Za-z0-9 _.,\-]", lab):
                        rep.warn(path, ln, f"unquoted mermaid label with special characters: {lab[:40]!r}")
                st = raw.strip()
                if st.startswith("subgraph"):
                    depth += 1
                elif st == "end":
                    depth -= 1
            if kind.startswith("stateDiagram") and "-->" in raw and ":" in raw and '"' in raw.split(":", 1)[1]:
                rep.warn(path, ln, "quotes in a state-diagram transition label")
        if depth != 0:
            rep.error(path, start, "subgraph/end mismatch in mermaid block")
        if kind in ("flowchart", "graph"):
            nodes, edges = mermaid_edges(lines)
            if is_linear(nodes, edges):
                rep.warn(path, start, "linear pipeline picture - show loops, hubs or parallel work instead")
            elif is_pipeline_in_disguise(nodes, edges):
                rep.warn(path, start, "pipeline in disguise: one path through most nodes and no hub - show hubs or parallel work")


def check_guards(files, rep: Report):
    guarded = [f for f in files if f.name != "AGENTS.md" and f.name != "CHANGELOG.md"
               and (f == ROOT / "README.md" or (f.parent == DOCS or f.parent == DOCS / "research"))]
    for f in guarded:
        text = f.read_text(encoding="utf-8")
        allow = rel(f) in ANCHOR_ALLOWLIST
        for n, line in enumerate(text.splitlines(), 1):
            if not allow:
                for pat in ANCHOR_PATTERNS:
                    if re.search(pat, line, re.I):
                        rep.error(f, n, f"anchoring guard: {pat!r} may appear only in the exam documents")
            for pat, flags in BLOAT_PATTERNS:
                if re.search(pat, line, flags):
                    rep.error(f, n, f"bloat guard: {pat!r} (no governance paperwork in ideation)")


def check_svgs(rep: Report):
    for p in sorted((DOCS / "img").glob("*.svg")) if (DOCS / "img").exists() else []:
        try:
            ET.parse(p)
        except ET.ParseError as e:
            rep.error(p, 1, f"malformed SVG: {e}")


def check_headings(files, parsed, rep: Report):
    for f in files:
        h1 = [h for h in parsed[f][2] if h[1] == 1]
        if len(h1) != 1:
            rep.warn(f, h1[1][0] if len(h1) > 1 else 1, f"expected exactly one H1, found {len(h1)}")


def run(strict: bool) -> int:
    rep = Report()
    files = live_files()
    parsed = {f: parse(f.read_text(encoding="utf-8")) for f in files}
    anchor_cache = {f: anchors_of(parsed[f][2]) for f in files}
    graph = check_links(files, parsed, anchor_cache, rep)
    check_orphans(files, graph, rep)
    for f in files:
        check_mermaid(f, parsed[f][1], rep)
    check_guards(files, rep)
    check_svgs(rep)
    check_headings(files, parsed, rep)
    for line in rep.errors + rep.warnings:
        print(line)
    failed = bool(rep.errors) or (strict and bool(rep.warnings))
    print(f"\n{len(files)} documents checked: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)"
          f"{' (strict)' if strict else ''} -> {'FAIL' if failed else 'OK'}")
    return 1 if failed else 0


def self_test() -> int:
    assert slugify("7. Staying current — the change radar") == "7-staying-current--the-change-radar"
    assert slugify("3. The Exam") == "3-the-exam"
    assert slugify("A `code` and [a link](x.md) title") == "a-code-and-a-link-title"
    assert anchors_of([(1, 2, "Same"), (2, 2, "Same")]) == {"same", "same-1"}
    n, e = mermaid_edges(["flowchart LR", 'A["x"] --> B["y"]', "B --> C", "C --> D", "D --> E"])
    assert is_linear(n, e)
    n, e = mermaid_edges(["flowchart LR", "A --> B", "B --> C", "C --> D", "D --> E", "E --> A"])
    assert not is_linear(n, e)
    n, e = mermaid_edges(["flowchart LR", "A --> B", "A --> C", "B --> D", "C --> D", "D --> E"])
    assert not is_linear(n, e)
    n, e = mermaid_edges(["flowchart TB", "A <--> B", "B --> C", "C --> D", "D --> E"])
    assert not is_linear(n, e)
    n, e = mermaid_edges(["flowchart LR", "A --> B", "B --> C", "C --> D", "D --> E", "E --> F", "F --> A"])
    assert is_pipeline_in_disguise(n, e)
    n, e = mermaid_edges(["flowchart TB", "H --> A", "H --> B", "H --> C", "H --> D", "A --> H", "B --> H", "C --> H"])
    assert not is_pipeline_in_disguise(n, e)
    print("self-test OK")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--self-test", action="store_true", help="run the built-in tests and exit")
    a = ap.parse_args()
    sys.exit(self_test() if a.self_test else run(a.strict))
