"""What code can say about the text of a query without the text leaving it: which table names it mentions, and whether it reads every table.

The text of a rule, a workbook or a saved search is text that somebody in the estate wrote, so it never goes to a model. These functions turn it into facts that code can count: the
names of the tables of one workspace that the text mentions as words, outside its comments and its strings. A mention is not proof that the table is read (a column or a variable
may have the name of a table), and a query that reads many tables at once (a search, a find, a union of everything) mentions none by name: `scans_every_table` says so.
"""
from __future__ import annotations

import re
from typing import Collection

MAX_TEXT = 200_000  # the characters of one text that are looked at
# A comment and a string are skipped in one pass, so that a quote in a comment and the two slashes of an address in a string are what they are: 'text', "text", @'verbatim', h'hidden'.
_SKIP = re.compile(r"//[^\n]*|[hH]?@?'(?:[^'\\]|\\.)*'|[hH]?@?\"(?:[^\"\\]|\\.)*\"")
_BRACKETED = re.compile(r"\[\s*(?:'([A-Za-z_][A-Za-z0-9_]*)'|\"([A-Za-z_][A-Za-z0-9_]*)\")\s*\]")  # ['Name'] and ["Name"] write a name that could be a keyword
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EVERYTHING = re.compile(r"\bunion\b(?:\s+(?:withsource\s*=\s*\w+|kind\s*=\s*\w+|isfuzzy\s*=\s*\w+))*\s+\*|\bsearch\b\s*(?:in\s*\(\s*\*\s*\)|\*|\")|\bfind\b\s*(?:in\s*\(\s*\*\s*\)|where\b|\")",
                         re.I)


def _plain(text: object) -> str:
    """The text without its comments and strings (a name between brackets is kept as the name)."""
    if not isinstance(text, str):
        return ""
    text = text[:MAX_TEXT]
    named = " ".join(first or second for first, second in _BRACKETED.findall(text))
    return f"{_SKIP.sub(lambda found: ' ' if found.group(0).startswith('//') else chr(34) * 2, text)} {named}"


def words_of(text: object) -> frozenset[str]:
    """The words of a text, outside its comments and strings, as they are written (a table name has a case)."""
    return frozenset(_WORD.findall(_plain(text)))


def mentioned(text: object, known: Collection[str]) -> frozenset[str]:
    """The names of `known` that the text has as a word, outside its comments and strings."""
    return frozenset(word for word in words_of(text) if word in known)


def scans_every_table(text: object) -> bool:
    """Whether the text reads every table at once, with a union of all of them, a search or a find, and so names none of them."""
    return bool(_EVERYTHING.search(_plain(text)))
