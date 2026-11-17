"""What a resource is connected to and what is connected to it: the references that the resources of the estate hold to one another, read from their own properties. Standard library only.
It holds ids, numbers and the words that the platform gives its keys, and it decides nothing.

A pass lists every resource with its properties from Resource Graph, a page at a time (the toolbox asks for the pages). Each page is walked and dropped: what is kept is the id of each resource and,
for each string in its properties that is an id (a path into a resource counts), the key that held it. After the last page each reference is resolved to the longest prefix that is the id of a resource of
the run: a path into a resource is an edge to that resource, a reference to something outside the run is counted and dropped, and a reference to itself is ignored. The structure of an id is an edge too:
a part is the `parent` of the resource that holds it. A key is the word of a relation only when it is a plain name of the platform; any other key is `other`.
"""
from __future__ import annotations

from typing import Iterable

QUERY = ("// meternaut:edges\nresources\n| project id, managedByText = tostring(managedBy), "
         "props = iff(tostring(properties) contains '/subscriptions/', properties, dynamic(null))")
PAGE = 1000  # rows of one page of Resource Graph
MAX_PAGES = 200  # pages of one pass
MAX_RESOURCES = 300_000  # resources whose ids are kept
MAX_REFS = 400_000  # references that wait for the last page
MAX_NODES = 5000  # values looked at in the properties of one resource
MAX_DEPTH = 10  # levels of a property that are followed
MAX_PER_RESOURCE = 500  # references of one resource
MAX_ID = 400  # characters of a string that may be an id
PARENT = "parent"
OTHER = "other"
START = "/subscriptions/"


def _toolbox():
    from . import toolbox  # the toolbox imports this module, so a top-level import would be circular

    return toolbox


def references(properties: object, managed_by: object = None) -> tuple[list[tuple[str, str]], bool]:
    """The strings of the properties that are ids, as (the key that held it, the string), and whether the walk was cut by a bound. The key is that of the value, and the key above it when that key
    is `id`. A string under a key that holds somebody's text is not an id, and such a key is not followed."""
    tb = _toolbox()
    found: list[tuple[str, str]] = []
    budget = [MAX_NODES]

    def word(key: str, above: str | None) -> str:
        name = above if key == "id" else key
        return name if name is not None and tb.KEY.fullmatch(name) and not tb._denied(name) else OTHER

    def walk(node: object, key: str | None, above: str | None, depth: int) -> None:
        budget[0] -= 1
        if budget[0] < 0 or len(found) > MAX_PER_RESOURCE:
            return
        if isinstance(node, str):
            if key is not None and len(node) <= MAX_ID and node[:len(START)].lower() == START and (key == "id" or not tb._denied(key)):
                found.append((word(key, above), node))
        elif depth < MAX_DEPTH and isinstance(node, dict):
            for name, value in node.items():
                if isinstance(name, str) and (not isinstance(value, (dict, list)) or not tb._denied(name)):
                    walk(value, name, key, depth + 1)
        elif depth < MAX_DEPTH and isinstance(node, list):
            for item in node:
                walk(item, key, above, depth + 1)

    walk(properties, None, None, 0)
    if isinstance(managed_by, str) and managed_by[:len(START)].lower() == START and len(managed_by) <= MAX_ID:
        found.append(("managedBy", managed_by))
    return found[:MAX_PER_RESOURCE], budget[0] < 0 or len(found) > MAX_PER_RESOURCE


def resolve(text: str, ids: dict[str, int]) -> int | None:
    """The number of the resource that a string names: the longest prefix of it that is the id of a resource of the run, so that a path into a resource is that resource."""
    parts = text.lower().split("/")
    for end in range(len(parts), 4, -1):
        number = ids.get("/".join(parts[:end]))
        if number is not None:
            return number
    return None


class Edges:
    """The pass over the estate: what is left to read (groups of subscriptions with the token of their next page), the ids and the references that were read, and, once every page is read, the edges."""

    def __init__(self, groups: list[list[str]]) -> None:
        self.todo: list[list] = [[group, None] for group in groups]
        self.subs = [sub for group in groups for sub in group]
        self.failed: list[str] = []
        self.error: Exception | None = None  # the first error that made a subscription unreadable
        self.ids: dict[str, int] = {}
        self.names: list[str] = []
        self.raw: list[tuple[int, str, str]] = []
        self.pages = self.outside = self.not_kept = 0
        self.done = False
        self.out: dict[int, list[tuple[int, str]]] = {}
        self.into: dict[int, list[tuple[int, str]]] = {}
        self.count = 0

    def add(self, rows: Iterable[dict]) -> None:
        """Walks the rows of one page and keeps the ids and the references. A resource that an earlier page of the pass gave is skipped."""
        for item in rows:
            key = str(item.get("id") or "").lower()
            if not key.startswith(START) or key in self.ids:
                continue
            if len(self.ids) >= MAX_RESOURCES:
                self.not_kept += 1
                continue
            number = self.ids[key] = len(self.names)
            self.names.append(key)
            found, cut = references(item.get("props"), item.get("managedByText"))
            self.not_kept += cut
            for text_word, text in found:
                if len(self.raw) >= MAX_REFS:
                    self.not_kept += 1
                else:
                    self.raw.append((number, text, text_word))

    def finish(self) -> None:
        """Resolves the references against every id that the pass read, and drops them."""
        tb = _toolbox()
        seen: set[tuple[int, int, str]] = set()

        def link(source: int, target: int, relation: str) -> None:
            if (source, target, relation) not in seen:
                seen.add((source, target, relation))
                self.out.setdefault(source, []).append((target, relation))
                self.into.setdefault(target, []).append((source, relation))

        for source, text, relation in self.raw:
            target = resolve(text, self.ids)
            if target is None:
                self.outside += tb.type_of_id(text) is not None
            elif target != source:
                link(source, target, relation)
        for number, key in enumerate(self.names):
            parent = resolve(key.rsplit("/", 2)[0], self.ids)
            if parent is not None and parent != number:
                link(number, parent, PARENT)
        self.count, self.raw, self.done = len(seen), [], True
