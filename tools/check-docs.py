#!/usr/bin/env python3
"""Documentation lint for Azure Cost in Action. Standard library only.

Checks
  1. Links and anchors in live documents resolve (GitHub heading-slug rules).
  2. Mermaid blocks: known diagram type, balanced quotes and brackets, quoted labels where
     needed, and no linear pipeline - a single chain, or one path through most nodes with no
     hub, even if closed into a ring (pictures must show loops, hubs, parallel work).
  3. SVG files are well-formed XML.
  4. Every live document is reachable from README.md (no orphans).
  5. Anchoring guard: the two findings that started the project may appear only in the cost-trap
     bank - never as the foundation of the design (AGENTS.md rule 6). Matching also works
     across hard-wrapped lines, and the text of the SVG pictures is scanned too.
  6. Bloat guard: no governance-paperwork vocabulary in the live documents (AGENTS.md rule 2).
  7. Purchase wording: purchases are prepared by the AI, approved by two named humans and executed
     by the AI (AGENTS.md rule 10); the older "executed by humans" wording is rejected.
  8. State diagrams: no ';' in a transition label (Mermaid ends the description there) and no
     straight-line state diagram without a back-edge.
  9. Live guards (every live document, ideation, design and experience): the vocabulary of ideas that
     were dropped (a lab, exams) and of the old names (Brief, Move), text addressed to the person who
     commissioned the project, and project history (versions, withdrawals) - none of it belongs in
     a document written for strangers (AGENTS.md rule 11 (c), (j), (k)).
 10. Card templates (docs/experience/cards/, tools/cardlint.py): Adaptive Card schema and size rules,
     the elements and actions Teams renders, labelled inputs, the AI label and footer, the three
     conversation verbs, a price basis and a saving word beside every money figure, one link only
     (the approval page), no urgency wording, invented sample data (AGENTS.md rule 13).

Limits (a guard is a safety net, not a substitute for judgement): AGENTS.md, CHANGELOG.md and
docs/reviews/ describe the rules and the review record, so the pattern guards skip them; paraphrase
can evade a pattern; a decorative hub can hide a pipeline; the link check ignores reference-style,
HTML and autolink forms (they raise a warning instead).

Scopes (AGENTS.md rule 11). The ideation documents (docs/*.md, docs/research/) get every ideation
guard. The design documents (docs/design/*.md) may name technologies and discuss security, governance
and decisions, so they get the phrase-level anchoring patterns (the project owner's two examples must
not appear), the "pointless questions" bloat terms and the purchase wording, plus the design guards
that the first design taught (AGENTS.md rule 11 a-d, g): write for the community (no personal
references, no "the operator"), never invent (no "assumptions", no hedge hardened into a ban on
Databricks or Fabric), plain words (no invented jargon), no review history, a size budget
(README and every document, and the whole design) and no wall of text (paragraph and table-row
length). The experience documents (docs/experience/*.md, AGENTS.md rule 13) get the same design
guards with their own budget (README and every document, and the whole folder) and the card
checks above. All scopes get the live guards. Anything under docs/design/ other than the documents
themselves (the price snapshot) is third-party data and is not checked.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cardlint  # noqa: E402  (the card-template checks of the experience design)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Documents in which the operator's original examples may legitimately appear.
ANCHOR_ALLOWLIST = {
    "docs/research/cost-trap-bank.md",
}
# Records of the ideation-v4 review rounds: their relative links point at the documents of that
# version, which now live only at the git tag `ideation-v4`, so link targets are not checked there.
FROZEN_RECORDS = ("docs/reviews/v4-round-1/", "docs/reviews/v4-round-2/")
ANCHOR_PATTERNS = [
    r"\bP2S\b", r"point[- ]to[- ]site", r"\bvWAN\b", r"virtual wan", r"LAQueryLogs",
    r"seed[- ]example", r"release[- ]1\b", r"log analytics",
    r"never reads?\b", r"nobody (?:ever )?(?:reads|queries|looks at)",
    r"no ?one (?:ever )?(?:reads|queries|looks at)", r"read by nobody",
    r"scaled up (?:years )?(?:long )?ago", r"never opened", r"not queried",
    r"idle gateway", r"shared gateway", r"unused logs", r"never queried",
    r"virtual hub", r"gateway scale units?", r"vpn gateway", r"azure monitor logs",
]
BLOAT_PATTERNS = [
    (r"kill criteri", re.I), (r"risk register", re.I), (r"assumption register", re.I),
    (r"decision register", re.I), (r"technical spike", re.I), (r"threat catalog", re.I),
    (r"honest unknowns", re.I), (r"exit criteria", re.I), (r"assumptions? list", re.I),
    (r"open questions? (?:for|to) the operator", re.I), (r"go\s*/\s*no-go", re.I),
    (r"risk log", re.I), (r"decision log", re.I),
    (r"threat model", re.I), (r"assumptions we are making", re.I), (r"abandon the idea", re.I),
    (r"R3-Data", 0), (r"\bK[1-7]\b", 0), (r"\bD(?:1[0-8]|[1-9])\b", 0),
]
PURCHASE_PATTERNS = [
    (r"executed by (?:the )?(?:named )?humans?", re.I),
    (r"humans? (?:execute|click|sign)s? the purchase", re.I),
]
# Design scope: phrase-level anchoring only (technology names such as Log Analytics or a virtual
# hub are ordinary design vocabulary), and only the "pointless questions" bloat terms.
DESIGN_ANCHOR_PATTERNS = [
    r"seed[- ]example", r"release[- ]1\b", r"never reads?\b",
    r"nobody (?:ever )?(?:reads|queries|looks at)", r"no ?one (?:ever )?(?:reads|queries|looks at)",
    r"read by nobody", r"scaled up (?:years )?(?:long )?ago", r"never opened",
    r"idle gateway", r"shared gateway", r"unused logs", r"never queried", r"\bLAQueryLogs\b",
]
DESIGN_BLOAT_PATTERNS = [
    (r"kill criteri", re.I), (r"open questions? (?:for|to) the operator", re.I),
    (r"go\s*/\s*no-go", re.I), (r"abandon the idea", re.I), (r"R3-Data", 0),
]
# Design guards (AGENTS.md rule 11): what the withdrawn first design taught. (pattern, message);
# matched case-insensitively across hard-wrapped lines, with link targets removed first.
DESIGN_FORBIDDEN = [
    (r"\b(?:the|our|an?) operator\b|\boperator(?:'s|s')|\boperator-declared\b",
     "write for the community: no 'the operator' (say 'the adopting organisation' or 'the platform team')"),
    (r"\b(?:my|his|her) (?:landing zone|tenant|subscriptions?|location)\b|\btinodo\b|\bTino\b|\bDonderwinkel\b"
     r"|\bproject owner\b",
     "no personal references in a document meant for a community"),
    (r"^#{1,6}\s.*\bassumptions?\b|\bwe assume\b|\bunder (?:the )?assumption\b|\bassumptions? (?:register|list|table|section)\b",
     "no assumptions section or list: call sizing numbers scenario parameters and decide the rest"),
    (r"\blicen[cs]es? (?:is |are )?assumed\b|\bno licen[cs]es? (?:is |are )?(?:assumed|held|owned)\b"
     r"|\bbeyond (?:the )?azure subscriptions?\b",
     "do not invent a licence position; state which feature needs which licence"),
    (r"\b(?:from|per|in|by|of|as) the (?:design )?brief\b|\bdesign brief\b",
     "do not cite 'the brief' in a design document"),
    (r"\b(?:no|without|exclud\w+|forbid\w*|bann?\w*)\s+(?:databricks|fabric)\b"
     r"|\b(?:databricks|fabric)\b[^.\n|]{0,50}\b(?:excluded|forbidden|not allowed|out of scope|by constraint)\b",
     "do not harden a hedge into a ban on Databricks or Fabric: say what each is for and when it earns a place"),
    (r"\bspine\b|\bleaf\b|\bagentic leaves\b|\bauthority chain\b|\bdoorbell\b",
     "plain words: no invented jargon"),
    (r"\bround [1-3]\b|\bthird pass\b|\bclosure (?:check|round|re-?check)\b|\brubber[- ]?duck\w*\b|\badversarial review\b",
     "review history belongs in docs/reviews, not in the design"),
]
# Live guards: every live document, ideation and design alike (AGENTS.md rule 11 (c), (j), (k)).
# (pattern, message, flags). Link targets and the names of real Azure products that contain a dropped
# word (DevTest Labs, Lab Services) are removed first; matching works across hard-wrapped lines.
LIVE_FORBIDDEN = [
    (r"\blabs?\b|\blaborator(?:y|ies)\b|\bterrariums?\b|\bwind[- ]tunnels?\b|\btime[- ]machines?\b"
     r"|\b(?:billing|signal) benche?s?\b|\brehearsal estates?\b|\bjanitor\b|\blab notebook\b|\bexperiment ledger\b",
     "no lab: the system builds nothing in order to learn, and a document never mentions that it might have", re.I),
    (r"\bexams?\b|\bexaminers?\b|\bexaminations?\b|\bforgers?\b|\bexperimenters?\b|\bcartographers?\b|\blearners?\b",
     "plain words: say 'evaluation' and 'sealed test cases', and name the real agent", re.I),
    (r"\byou said\b|\byour starting constraints\b|\bthe brief\b|\brubber[- ]?duck\w*\b|\bproject owner\b|\bthe commissioner\b"
     r"|\bprivate until\b|\buntil you say\b|\bunless you say\b",
     "a document is for its readers: never address, quote or answer the person who commissioned the project", re.I),
    (r"\bdesign-v\d|\bideation-v\d|\b(?:first|earlier|previous) (?:design|draft)\b|\b(?:was|were|been) withdrawn\b",
     "history belongs in the changelog and the review record, not in the documents", re.I),
    (r"\bjudged on merit\b|\bnot ruled out\b",
     "do not answer a question nobody asked: say what a technology is for and when it earns a place", re.I),
    (r"\breview rounds?\b|\bround[- ][1-3]\b|\bcorrected (?:after|in) (?:review )?rounds?\b|\bclosure checks?\b|\bthird pass\b",
     "review history belongs in docs/reviews, not in the documents", re.I),
    (r"\bBriefs?\b", "say 'Recommendation'", 0),
    (r"\bMoves\b|\b(?:a|an|the|each|every|new|tested|ordinary) Move\b|\bMove Workshop\b", "say 'Action'", 0),
    (r"\breplay\s*(?:,|·|→|/|\|)\s*(?:and\s+)?watch\b",
     "the route is called Follow (ask, look, replay, follow, pool, trial); only the Watch clock and workflow keep 'watch'", re.I),
    (r"\bUnexplained Spend Ledger\b", "say 'Unexplained Spend list': the Ledger records predictions, decisions and outcomes", 0),
    (r"\bbill-confirmed\b", "say 'bill-observed' (the four evidence levels)", re.I),
]
# Ideation guards (AGENTS.md rule 12): a customer's commercial arrangement is an agreement, never a contract.
# 'contract' survives only in the title 'the learning contract' and in 'contracted rates' (not matched).
IDEATION_FORBIDDEN = [
    (r"(?<!learning )\bcontracts?\b",
     "say 'agreement' for the customer's commercial arrangement; 'contract' survives only in 'the learning contract' "
     "and 'contracted rates'", re.I),
]
PRODUCT_NAMES = re.compile(r"\b(?:Azure )?(?:DevTest Labs|Lab Services)\b", re.I)
BANK_ROW = re.compile(r"^\|\s*TRAP-[A-Z0-9]+-\d{3}\s*\|")
# '78 Verified' / '78 of the 145 Verified' before the status, or 'Verified (78)' / '`Verified` (78 of the 145)' after it
BANK_STATUS_CLAIM = re.compile(
    r"\b(\d+)(?: of the 145)?\s+\*?(Verified|Partial|Unverified)\b"
    r"|\b(Verified|Partial|Unverified)\b`?\*?\s*\((\d+)(?: of the 145)?\)")
LINK_TARGET = re.compile(r"\]\([^)\n]*\)")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
DESIGN_MAX_WORDS_README = 1800
DESIGN_MAX_WORDS_DOC = 6000
DESIGN_MAX_WORDS_TOTAL = 49000
EXPERIENCE_MAX_WORDS_TOTAL = 38500
# scope -> (the folder's README, the limit for the whole folder); both folders share the per-document limits
BUDGETS = {
    "design": ("docs/design/README.md", DESIGN_MAX_WORDS_TOTAL),
    "experience": ("docs/experience/README.md", EXPERIENCE_MAX_WORDS_TOTAL),
}
DESIGN_MAX_PARAGRAPH_CHARS = 1100
DESIGN_MAX_TABLE_ROW_CHARS = 800
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
        if f.resolve().relative_to(ROOT).as_posix().startswith(FROZEN_RECORDS):
            continue
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
        if f.name not in ("README.md", "AGENTS.md", "CHANGELOG.md") and f not in seen:
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
        clean = re.sub(r"(?<![-=.])--\s+.+?\s+-->", "-->", clean)
        clean = re.sub(r"(?<![-=.])-\.\s+.+?\s+\.->", "-.->", clean)
        clean = re.sub(r"(?<![-=.])==\s+.+?\s+==>", "==>", clean)
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
    """One path through at least 70% of the nodes and no hub: a chain, even if closed into a ring."""
    if len(nodes) < 6 or len(nodes) > 24:
        return False
    return longest_path_nodes(nodes, edges) >= 0.7 * len(nodes) and max_degree(nodes, edges) < 4


STATE_EDGE = re.compile(r"^\s*(\[\*\]|[A-Za-z_]\w*)\s*-->\s*(\[\*\]|[A-Za-z_]\w*)")


def state_edges(lines):
    nodes, edges = set(), set()
    for raw in lines:
        m = STATE_EDGE.match(raw)
        if not m:
            continue
        a, b = m.groups()
        nodes.update(x for x in (a, b) if x != "[*]")
        if "[*]" not in (a, b):
            edges.add((a, b))
    return nodes, edges


def has_cycle(nodes, edges) -> bool:
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        state[n] = 1
        for m in adj[n]:
            if state.get(m) == 1 or (m not in state and visit(m)):
                return True
        state[n] = 2
        return False

    return any(n not in state and visit(n) for n in nodes)


def is_straight_state_line(nodes, edges) -> bool:
    """A state diagram with no back-edge, one path through most states and no hub."""
    if len(nodes) < 6 or has_cycle(nodes, edges):
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
            if kind.startswith("stateDiagram") and "-->" in raw and ":" in raw:
                label = raw.split(":", 1)[1]
                if '"' in label:
                    rep.warn(path, ln, "quotes in a state-diagram transition label")
                if ";" in label:
                    rep.error(path, ln, "semicolon in a state-diagram transition label (Mermaid ends the description at ';')")
            if kind == "sequenceDiagram" and re.search(r"-{1,2}>>?|--x|--\)", raw) and ":" in raw:
                if ";" in raw.split(":", 1)[1]:
                    rep.error(path, ln, "semicolon in a sequence-diagram message (Mermaid ends the statement at ';')")
        if depth != 0:
            rep.error(path, start, "subgraph/end mismatch in mermaid block")
        if kind.startswith("stateDiagram"):
            snodes, sedges = state_edges(lines)
            if is_straight_state_line(snodes, sedges):
                rep.warn(path, start, "state diagram is a straight line - show back-edges (declined, rolled back, re-opened)")
        if kind in ("flowchart", "graph"):
            nodes, edges = mermaid_edges(lines)
            if is_linear(nodes, edges):
                rep.warn(path, start, "linear pipeline picture - show loops, hubs or parallel work instead")
            elif is_pipeline_in_disguise(nodes, edges):
                rep.warn(path, start, "pipeline in disguise: one path through most nodes and no hub - show hubs or parallel work")


def paragraph_hits(text: str, pat: str, flags: int = re.I):
    """Yield (line, matched text) for a pattern found in a paragraph, even across hard-wrapped lines."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip():
            j += 1
        joined, offsets = "", []
        for k in range(i, j):
            offsets.append((len(joined), k + 1))
            joined += lines[k].strip() + " "
        for m in re.finditer(pat, joined, flags):
            yield next(n for off, n in reversed(offsets) if off <= m.start()), m.group(0)
        i = j


def guarded_files(files):
    """Every live document except the files that describe the rules and the review record."""
    return [f for f in files if f.name not in ("AGENTS.md", "CHANGELOG.md")
            and "reviews" not in f.resolve().relative_to(ROOT).parts]


def scope_of(f: Path) -> str:
    """'ideation' (default), 'design' (docs/design/*.md), 'experience' (docs/experience/*.md) or
    'evidence' (anything deeper in those two folders: the price snapshot, the card templates)."""
    parts = f.resolve().relative_to(ROOT).parts
    if len(parts) >= 3 and parts[0] == "docs" and parts[1] in ("design", "experience"):
        return parts[1] if len(parts) == 3 else "evidence"
    return "ideation"


def check_guards(files, rep: Report):
    for f in guarded_files(files):
        text = f.read_text(encoding="utf-8")
        scope = scope_of(f)
        anchors = ANCHOR_PATTERNS if scope == "ideation" else DESIGN_ANCHOR_PATTERNS
        bloat = BLOAT_PATTERNS if scope == "ideation" else DESIGN_BLOAT_PATTERNS
        if scope != "evidence" and rel(f) not in ANCHOR_ALLOWLIST:
            seen = set()
            for pat in anchors:
                for n, _hit in paragraph_hits(text, pat):
                    if (n, pat) not in seen:
                        seen.add((n, pat))
                        rep.error(f, n, f"anchoring guard: {pat!r} may appear only in the cost-trap bank")
        if scope != "evidence":
            for n, msg, hit in live_text_problems(text):
                rep.error(f, n, f"live guard: {msg} [{hit}]")
        if scope == "ideation":
            for n, msg, hit in live_text_problems(text, IDEATION_FORBIDDEN):
                rep.error(f, n, f"live guard: {msg} [{hit}]")
        for n, line in enumerate(text.splitlines(), 1):
            if scope != "evidence":
                for pat, flags in bloat:
                    if re.search(pat, line, flags):
                        rep.error(f, n, f"bloat guard: {pat!r} (no governance paperwork in ideation)")
            for pat, flags in PURCHASE_PATTERNS:
                if re.search(pat, line, flags):
                    rep.error(f, n, "purchase wording: prepared by the AI, approved by two named humans, executed by the AI (AGENTS.md rule 10)")


def live_text_problems(text: str, rules=None):
    """(line, message, matched text) for every live-guard violation; link targets and the names of
    real Azure products that contain a dropped word (DevTest Labs, Lab Services) are ignored."""
    clean = PRODUCT_NAMES.sub("", LINK_TARGET.sub("]()", text))
    found: dict = {}
    for pat, msg, flags in (LIVE_FORBIDDEN if rules is None else rules):
        for n, hit in paragraph_hits(clean, pat, flags):
            found.setdefault((n, msg), hit.strip())
    return sorted((n, msg, hit) for (n, msg), hit in found.items())


def design_text_problems(text: str):
    """(line, message) for every design vocabulary violation in a document (link targets are ignored)."""
    clean = LINK_TARGET.sub("]()", text)
    found = set()
    for pat, msg in DESIGN_FORBIDDEN:
        for n, _hit in paragraph_hits(clean, pat):
            found.add((n, msg))
    return sorted(found)


def prose_blocks(prose):
    """(first line, kind, characters) for each paragraph, list item and table row; `prose` excludes code fences."""
    out, cur, last = [], None, 0
    for n, raw in prose:
        line = raw.strip()
        if cur and (not line or n != last + 1):
            out.append(tuple(cur))
            cur = None
        last = n
        if not line:
            continue
        if line.startswith("|"):
            if cur:
                out.append(tuple(cur))
                cur = None
            out.append((n, "table row", len(line)))
        elif cur is None or LIST_ITEM.match(raw):
            if cur:
                out.append(tuple(cur))
            cur = [n, "paragraph", len(line)]
        else:
            cur[2] += len(line) + 1
    if cur:
        out.append(tuple(cur))
    return out


def check_design(files, parsed, rep: Report):
    """Vocabulary, size and wall-of-text guards for the design (docs/design/*.md) and the
    experience design (docs/experience/*.md); each folder has its own total."""
    totals = {scope: 0 for scope in BUDGETS}
    for f in files:
        scope = scope_of(f)
        if scope not in BUDGETS:
            continue
        for n, msg in design_text_problems(f.read_text(encoding="utf-8")):
            rep.error(f, n, f"{scope} guard: {msg}")
        prose = parsed[f][0]
        words = sum(len(line.split()) for _, line in prose)
        totals[scope] += words
        cap = DESIGN_MAX_WORDS_README if f.name == "README.md" else DESIGN_MAX_WORDS_DOC
        if words > cap:
            rep.error(f, 1, f"size budget: {words} words, the limit is {cap} - cut, do not squeeze")
        for n, kind, size in prose_blocks(prose):
            limit = DESIGN_MAX_TABLE_ROW_CHARS if kind == "table row" else DESIGN_MAX_PARAGRAPH_CHARS
            if size > limit:
                rep.warn(f, n, f"{kind} of {size} characters (limit {limit}) - split it or turn it into a table")
    for scope, (readme, limit) in BUDGETS.items():
        if totals[scope] > limit:
            rep.error(ROOT / readme, 1, f"size budget: the {scope} is {totals[scope]} words in total, the limit is {limit}")


def bank_counts(text: str) -> dict:
    """Status counts of the cost-trap bank: one table row per trap, the status in the last cell."""
    counts = {"Verified": 0, "Partial": 0, "Unverified": 0}
    for line in text.splitlines():
        if BANK_ROW.match(line):
            found = re.match(r"\W*(Verified|Partial|Unverified)\b", line.strip().strip("|").split("|")[-1])
            if found:
                counts[found.group(1)] += 1
    return counts


def check_bank_counts(files, rep: Report):
    """Every document that quotes the bank's status counts must quote the bank's own."""
    bank = DOCS / "research" / "cost-trap-bank.md"
    if not bank.exists():
        return
    counts = bank_counts(bank.read_text(encoding="utf-8"))
    for f in guarded_files(files):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in BANK_STATUS_CLAIM.finditer(line):
                number, status = int(m.group(1) or m.group(4)), m.group(2) or m.group(3)
                if number != counts[status]:
                    rep.error(f, n, f"bank count: says {number} {status}, the cost-trap bank has {counts[status]}")


def check_svgs(rep: Report):
    for p in sorted((DOCS / "img").glob("*.svg")) if (DOCS / "img").exists() else []:
        try:
            tree = ET.parse(p)
        except ET.ParseError as e:
            rep.error(p, 1, f"malformed SVG: {e}")
            continue
        words = " ".join(t.strip() for t in tree.getroot().itertext() if t.strip())
        for pat in ANCHOR_PATTERNS:
            if re.search(pat, words, re.I):
                rep.error(p, 1, f"anchoring guard in SVG text: {pat!r}")
        for pat, flags in BLOAT_PATTERNS:
            if re.search(pat, words, flags):
                rep.error(p, 1, f"bloat guard in SVG text: {pat!r}")


UNCHECKED_LINKS = re.compile(r"\]\[[^\]]*\]|<a\s+href=|<https?://", re.I)


def check_cards(rep: Report):
    """The Adaptive Card templates of the experience design (docs/experience/cards)."""
    for path, msg in cardlint.check():
        rep.error(path, 1, f"card guard: {msg}")


def check_link_forms(files, parsed, rep: Report):
    for f in files:
        if scope_of(f) == "evidence":
            continue
        for n, line in parsed[f][0]:
            if UNCHECKED_LINKS.search(INLINE_CODE.sub("", line)):
                rep.warn(f, n, "link form this lint does not check (reference-style, HTML or autolink) - use an inline [text](target) link")


def check_headings(files, parsed, rep: Report):
    for f in files:
        if scope_of(f) == "evidence":
            continue
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
    check_design(files, parsed, rep)
    check_svgs(rep)
    check_cards(rep)
    check_bank_counts(files, rep)
    check_link_forms(files, parsed, rep)
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
    n, e = mermaid_edges(["flowchart LR", "A -- go --> B", "B -- next step --> C", "C --> D", "D -. maybe .-> E", "E --> F", "F --> G"])
    assert ("A", "B") in e and ("B", "C") in e and ("D", "E") in e and is_pipeline_in_disguise(n, e)
    n, e = mermaid_edges(["flowchart LR", "A --> B", "B --> C", "C --> D", "D --> E", "E --> F", "F --> G", "C --> X", "D --> Y", "E --> Z"])
    assert is_pipeline_in_disguise(n, e)  # a 7-chain with three leaves is still a pipeline
    sn, se = state_edges(["stateDiagram-v2", "    [*] --> A: start", "    A --> B", "    B --> C", "    C --> D", "    D --> E", "    E --> F", "    F --> [*]"])
    assert is_straight_state_line(sn, se)
    sn, se = state_edges(["    [*] --> A", "    A --> B", "    B --> C", "    C --> D", "    D --> E", "    E --> F", "    F --> A: back-edge"])
    assert not is_straight_state_line(sn, se)
    probe = Report()
    check_mermaid(Path("probe.md"), [("mermaid", 1, ["stateDiagram-v2", "    A --> B: one; two"])], probe)
    assert any("semicolon" in m for m in probe.errors)
    probe2 = Report()
    check_mermaid(Path("probe.md"), [("mermaid", 1, ["sequenceDiagram", "    A->>B: one; two"])], probe2)
    assert any("semicolon" in m for m in probe2.errors)
    assert list(paragraph_hits("it was scaled up\nlong ago by someone", r"scaled up (?:years )?(?:long )?ago"))
    assert any(re.search(p, "a Go / no-go gate", f) for p, f in BLOAT_PATTERNS)
    assert any(re.search(p, "a purchase is executed by humans", f) for p, f in PURCHASE_PATTERNS)
    assert UNCHECKED_LINKS.search("see [text][ref] here")
    assert scope_of(ROOT / "docs" / "design" / "03-x.md") == "design"
    assert scope_of(ROOT / "docs" / "design" / "research" / "citadel.md") == "evidence"
    assert scope_of(ROOT / "docs" / "experience" / "04-x.md") == "experience"
    assert scope_of(ROOT / "docs" / "experience" / "cards" / "x.md") == "evidence"
    assert scope_of(ROOT / "docs" / "05-x.md") == "ideation"
    assert not any(re.search(p, "a Log Analytics workspace behind a virtual hub", re.I) for p in DESIGN_ANCHOR_PATTERNS)
    assert any(re.search(p, "a stream nobody reads", re.I) for p in DESIGN_ANCHOR_PATTERNS)
    bad = [
        "the operator approves", "Our Operator decides", "the operator's tenant", "operator-declared constraint",
        "my landing zone", "Tino approves", "the project owner wants", "## Assumptions", "We assume a hub exists",
        "under assumption A1", "the assumption list", "No licence is assumed", "beyond Azure subscriptions",
        "from the brief",
        "no Databricks", "Fabric is excluded", "Databricks is out of scope", "the spine of the system",
        "an agentic leaf", "added in round 2", "after the third pass", "a rubber duck reviewed it",
    ]
    for text in bad:
        assert design_text_problems(text), f"design guard missed: {text!r}"
    good = [
        "the adopting organisation approves", "Kubernetes operators", "an evaluation of the agents",
        "the saving assumes steady load", "scenario parameters", "[cost-trap bank](../research/cost-trap-bank.md)",
        "Entra ID P1 is required for Conditional Access", "a design review",
    ]
    for text in good:
        assert not design_text_problems(text), f"design guard false positive: {text!r}"
    live_bad = [
        "the Lab runs recipes", "a lab subscription", "lab-based experiments", "How it learns without a lab",
        "no lab: nothing is deployed to experiment", "instead of a lab", "the exam questions", "the Examiner",
        "the Terrarium", "a wind tunnel", "the Time Machine", "the Experimenter", "a slow learner",
        "you said it first", "Your starting constraints", "from the brief", "the project owner", "a rubber duck",
        "was withdrawn the same day", "see design-v1", "the first design", "judged on merit", "not ruled out",
        "a Brief card", "the Brief", "a Move", "the Moves", "Move Workshop",
        "Ask · Look · Replay · Watch · Pool", "ask, look, replay, watch, pool", "Replay → Watch",
        "the Unexplained Spend Ledger", "a bill-confirmed saving",
    ]
    for text in live_bad:
        assert live_text_problems(text), f"live guard missed: {text!r}"
    live_good = [
        "Azure DevTest Labs", "Azure Lab Services retires", "an evaluation of the agents", "a brief summary",
        "briefly", "move the database now", "label", "collaboration", "an example",
        "[cost-trap bank](../research/cost-trap-bank.md)",
        "replay history and watch the bill", "the Watch clock runs every hour", "the Unexplained Spend list",
        "a bill-observed saving",
    ]
    for text in live_good:
        assert not live_text_problems(text), f"live guard false positive: {text!r}"
    for text in ["under each contract", "the contract type", "the customer's contract", "a Contract renewal"]:
        assert live_text_problems(text, IDEATION_FORBIDDEN), f"ideation guard missed: {text!r}"
    for text in ["the learning contract", "The Learning Contract", "contracted rates", "a contracted price",
                 "[learning](09-the-learning-contract.md)"]:
        assert not live_text_problems(text, IDEATION_FORBIDDEN), f"ideation guard false positive: {text!r}"
    assert live_text_problems("the Lab\ncontroller")  # a phrase split over two lines is still found
    sample = "\n".join(["| ID | Trap | Status |", "|---|---|---|", "| TRAP-A-001 | x | Verified |",
                        "| TRAP-A-002 | x | Partial (a note) |", "| TRAP-A-003 | x | Verified *(a note)* |",
                        "| TRAP-A-004 | x | Unverified |"])
    assert bank_counts(sample) == {"Verified": 2, "Partial": 1, "Unverified": 1}
    assert [m.group(0) for m in BANK_STATUS_CLAIM.finditer("78 Verified, 33 Partial and 33 Unverified")] == ["78 Verified", "33 Partial", "33 Unverified"]
    assert BANK_STATUS_CLAIM.search("Rows marked `Verified` (78 of the 145) become gold") and BANK_STATUS_CLAIM.search("`Partial` (34)")
    assert not BANK_STATUS_CLAIM.search("the Verified rows become gold")
    blocks = prose_blocks([(1, "# T"), (2, ""), (3, "x" * 600), (4, "y" * 600), (5, ""), (6, "- item"), (7, "  more"),
                           (8, "| a | b |"), (9, "|---|---|"), (10, "| " + "z" * 900 + " |"), (12, "after a fence")])
    assert (3, "paragraph", 1201) in blocks and (6, "paragraph", 11) in blocks
    assert any(k == "table row" and s > DESIGN_MAX_TABLE_ROW_CHARS for _, k, s in blocks)
    assert (12, "paragraph", 13) in blocks
    assert cardlint.self_test() == 0
    print("self-test OK")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--self-test", action="store_true", help="run the built-in tests and exit")
    a = ap.parse_args()
    sys.exit(self_test() if a.self_test else run(a.strict))
