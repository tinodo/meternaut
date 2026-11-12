"""A structural check of an Adaptive Card of schema 1.4, with the standard library (cards.py makes the cards, and this checks them).

The card tooling of the repository (tools/render-cards) needs node packages that the build machines cannot install, so a card is checked here against what the public schema
(https://adaptivecards.microsoft.com/schemas/adaptive-card.json, read on 2026-11-08) says about the elements and actions that cards.py uses, and against the rules of this project that a machine can check.
The check is narrower than the schema on purpose: an element or action that cards.py does not use is an error (no Action.Submit, no Action.Execute, no input, image or table: the action that posts the
card takes no answer, so a button opens a page of the app or shows and hides a part of the card), and so is a property that the schema does not list (a renderer would ignore a typo). A link is the page of
one request, a button that answers it (cardlinks.py) or the start page of the web page, and nothing else. A hidden part must be shown by a button. The version is 1.4: Microsoft's tracker reports that
the posting actions of Power Automate render only up to 1.4 (https://github.com/microsoft/AdaptiveCards/issues/8965, read on 2026-11-11), the Teams reference says 1.5, and a 1.4 card renders in both
(Action.ToggleVisibility and isVisible are from 1.2; the style heading of a TextBlock, 1.5, is not used).

`check(card)` returns the problems as plain lines with the path of each; an empty list means that the card passes.
"""
from __future__ import annotations

import json
import re
import unicodedata

from . import cardlinks

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
VERSION = "1.4"
MAX_BYTES = 20000  # the message of the Teams actions of Power Automate is at most about 28 KB (Learn, "Microsoft Teams connector", read on 2026-11-11); a card of this repository stays far below it
MAX_ACTIONS = 6  # the answers, the page of the request and the two buttons of the question for a change that cannot be undone
HIDDEN = ("Cc", "Cf", "Cs", "Co", "Cn")

ENUMS = {
    "color": {"default", "dark", "light", "accent", "good", "warning", "attention"},
    "size": {"default", "small", "medium", "large", "extralarge"},
    "weight": {"default", "lighter", "bolder"},
    "spacing": {"default", "none", "small", "medium", "large", "extralarge", "padding"},
    "style_container": {"default", "emphasis", "good", "attention", "warning", "accent"},
    "style_action": {"default", "positive", "destructive"},
    "mode": {"primary", "secondary"},
    "horizontalalignment": {"left", "center", "right"},
    "teams_width": {"full"},
}
COMMON = {"id": "str", "isVisible": "bool", "separator": "bool", "spacing": "spacing", "height": "height", "fallback": "any", "requires": "dict"}
ELEMENTS = {
    "TextBlock": {**COMMON, "text": "str", "color": "color", "isSubtle": "bool", "maxLines": "int", "size": "size", "weight": "weight", "wrap": "bool",
                  "horizontalAlignment": "horizontalalignment", "fontType": "any"},
    "ColumnSet": {**COMMON, "columns": "columns", "style": "style_container", "bleed": "bool", "minHeight": "str", "horizontalAlignment": "horizontalalignment"},
    "Column": {**COMMON, "items": "items", "width": "width", "style": "style_container", "bleed": "bool", "minHeight": "str", "verticalContentAlignment": "any"},
    "Container": {**COMMON, "items": "items", "style": "style_container", "bleed": "bool", "minHeight": "str", "verticalContentAlignment": "any"},
    "FactSet": {**COMMON, "facts": "facts"},
    "ActionSet": {**COMMON, "actions": "actions"},
}
ACTION_COMMON = {"id": "str", "title": "str", "style": "style_action", "tooltip": "str", "isEnabled": "bool", "mode": "mode", "requires": "dict"}
ACTIONS = {
    "Action.OpenUrl": {**ACTION_COMMON, "url": "str"},
    "Action.ToggleVisibility": {**ACTION_COMMON, "targetElements": "targets"},
}
ROOT = {"type", "$schema", "version", "fallbackText", "body", "actions", "msteams", "lang", "speak"}
REQUIRED = {"TextBlock": {"text"}, "FactSet": {"facts"}, "ActionSet": {"actions"}, "Container": {"items"}, "Action.OpenUrl": {"url"}, "Action.ToggleVisibility": {"targetElements"}}
HTTPS = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%/-]*)?")


def _kind(value: object) -> str:
    return "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "float" if isinstance(value, float) else type(value).__name__


class _Check:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.ids: set[str] = set()
        self.element_ids: set[str] = set()
        self.pages: set[str] = set()
        self.answers: list[tuple[str, str]] = []  # (the answer, the page) of every link that answers
        self.targets: list[tuple[str, str, bool]] = []  # (where, element id, whether the button shows it)
        self.hidden: list[tuple[str, str | None]] = []  # (where, id) of every element that starts hidden
        self.actions_seen = 0

    def add(self, path: str, text: str) -> None:
        self.problems.append(f"{path}: {text}")

    # -- values --------------------------------------------------------------------------------------------------------------------------------
    def text(self, path: str, value: object) -> None:
        if not isinstance(value, str):
            self.add(path, f"must be a string, not {_kind(value)}")
            return
        if any(unicodedata.category(ch) in HIDDEN for ch in value):
            self.add(path, "has a control, direction, zero-width or unassigned character")

    def value(self, path: str, rule: str, value: object, container: str) -> None:
        if rule == "str":
            self.text(path, value)
        elif rule == "bool":
            if not isinstance(value, bool):
                self.add(path, f"must be true or false, not {_kind(value)}")
        elif rule == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                self.add(path, f"must be a whole number, not {_kind(value)}")
        elif rule in ENUMS or (rule == "style" and container in ("Container", "ColumnSet", "Column")):
            allowed = ENUMS["style_container" if rule == "style" else rule]
            if not isinstance(value, str) or value.lower() not in allowed:
                self.add(path, f"must be one of {sorted(allowed)}")
        elif rule == "height":
            if value not in ("auto", "stretch"):
                self.add(path, "must be auto or stretch")
        elif rule == "width":
            if not (value in ("auto", "stretch") or (isinstance(value, (int, float)) and not isinstance(value, bool)) or (isinstance(value, str) and re.fullmatch(r"\d{1,4}px", value))):
                self.add(path, "must be auto, stretch, a number or a width in px")
        elif rule == "dict":
            if not isinstance(value, dict):
                self.add(path, "must be an object")

    # -- structure -----------------------------------------------------------------------------------------------------------------------------
    def element(self, path: str, node: object, inside_column: bool = False) -> None:
        if not isinstance(node, dict):
            self.add(path, "must be an object")
            return
        kind = node.get("type")
        if kind not in ELEMENTS:
            self.add(path, f"the element type {kind!r} is not one that cards use")
            return
        spec = ELEMENTS[kind]
        for name, value in node.items():
            if name == "type":
                continue
            if name not in spec:
                self.add(f"{path}.{name}", f"is not a property of {kind}")
                continue
            if name == "id":
                self.text(f"{path}.id", value)
                if isinstance(value, str):
                    if value in self.ids:
                        self.add(f"{path}.id", f"the id {value!r} is used twice")
                    self.ids.add(value)
                    self.element_ids.add(value)
            elif name == "fallback":
                self.add(f"{path}.fallback", "an element that needs a fallback is not used")
            elif name == "requires":
                self.add(f"{path}.requires", "an element that needs a feature check is not used")
            elif spec[name] == "items":
                self.items(f"{path}.items", value)
            elif spec[name] == "columns":
                self.columns(f"{path}.columns", value)
            elif spec[name] == "facts":
                self.facts(f"{path}.facts", value)
            elif spec[name] == "actions":
                self.actions(f"{path}.actions", value)
            else:
                self.value(f"{path}.{name}", "style" if name == "style" else spec[name], value, kind)
        for name in REQUIRED.get(kind, ()):
            if name not in node:
                self.add(path, f"{kind} needs {name}")
        if node.get("isVisible") is False:
            self.hidden.append((path, node.get("id") if isinstance(node.get("id"), str) else None))
        if kind == "TextBlock":
            if node.get("wrap") is not True:
                self.add(path, "wrap must be true, so that no text is cut")
            if isinstance(node.get("text"), str) and not node["text"].strip():
                self.add(path, "a TextBlock has no text")
        if kind == "ActionSet" and isinstance(node.get("actions"), list) and not node["actions"]:
            self.add(path, "an ActionSet has no action")
        if kind == "FactSet" and isinstance(node.get("facts"), list) and not node["facts"]:
            self.add(path, "a FactSet has no fact")

    def items(self, path: str, value: object) -> None:
        if not isinstance(value, list) or not value:
            self.add(path, "must be a list with at least one element")
            return
        for index, item in enumerate(value):
            self.element(f"{path}[{index}]", item)

    def columns(self, path: str, value: object) -> None:
        if not isinstance(value, list) or not value:
            self.add(path, "must be a list with at least one column")
            return
        for index, item in enumerate(value):
            if not isinstance(item, dict) or item.get("type") != "Column":
                self.add(f"{path}[{index}]", "must be a Column")
            else:
                self.element(f"{path}[{index}]", item, inside_column=True)

    def facts(self, path: str, value: object) -> None:
        if not isinstance(value, list):
            self.add(path, "must be a list")
            return
        for index, fact in enumerate(value):
            where = f"{path}[{index}]"
            if not isinstance(fact, dict) or set(fact) != {"title", "value"}:
                self.add(where, "a fact has a title and a value and nothing else")
                continue
            for name in ("title", "value"):
                self.text(f"{where}.{name}", fact[name])
                if isinstance(fact[name], str) and not fact[name].strip():
                    self.add(f"{where}.{name}", "is empty")

    def actions(self, path: str, value: object) -> None:
        if not isinstance(value, list):
            self.add(path, "must be a list")
            return
        for index, node in enumerate(value):
            self.action(f"{path}[{index}]", node)

    def action(self, path: str, node: object) -> None:
        if not isinstance(node, dict):
            self.add(path, "must be an object")
            return
        kind = node.get("type")
        if kind not in ACTIONS:
            self.add(path, f"the action type {kind!r} is not one that cards use (a card that a flow posts takes no answer: no Action.Submit, no Action.Execute)")
            return
        self.actions_seen += 1
        spec = ACTIONS[kind]
        for name, value in node.items():
            if name == "type":
                continue
            if name not in spec:
                self.add(f"{path}.{name}", f"is not a property of {kind}")
            elif name == "requires":
                self.add(f"{path}.requires", "an action that needs a feature check is not used")
            elif name == "id":
                self.text(f"{path}.id", value)
                if isinstance(value, str):
                    if value in self.ids:
                        self.add(f"{path}.id", f"the id {value!r} is used twice")
                    self.ids.add(value)
            elif spec[name] == "targets":
                self.targets_of(f"{path}.targetElements", value)
            else:
                self.value(f"{path}.{name}", spec[name], value, kind)
        if not str(node.get("title", "")).strip():
            self.add(path, "an action has a title")
        for name in REQUIRED.get(kind, ()):
            if name not in node:
                self.add(path, f"{kind} needs {name}")
        if kind == "Action.OpenUrl":
            self.link(f"{path}.url", node.get("url"))
        if kind == "Action.ToggleVisibility" and not str(node.get("tooltip", "")).strip():
            self.add(path, "needs a tooltip: a screen reader says it")

    def link(self, path: str, url: object) -> None:
        """A link is the page of a request, the start page of the web page, or a button that answers a request (cardlinks.py): nothing else."""
        if not isinstance(url, str):
            self.add(path, "must be an https address")
            return
        found = cardlinks.ANSWER_ADDRESS.fullmatch(url)
        if found is not None:
            self.answers.append((found["verb"], found["page"]))
            self.pages.add(found["page"])
        elif HTTPS.fullmatch(url):
            self.pages.add(url)
        else:
            self.add(path, "must be an https address: the page of a request or one of its answer buttons")

    def targets_of(self, path: str, value: object) -> None:
        if not isinstance(value, list) or not value:
            self.add(path, "must be a list with at least one target")
            return
        for index, item in enumerate(value):
            where = f"{path}[{index}]"
            if not isinstance(item, dict) or set(item) != {"elementId", "isVisible"} or not isinstance(item["elementId"], str) or not isinstance(item["isVisible"], bool):
                self.add(where, "a target is an element id and true (show) or false (hide), and nothing else")
                continue
            self.targets.append((where, item["elementId"], item["isVisible"]))

    def toggles(self) -> None:
        """A button may name elements only, and what starts hidden must be shown by a button."""
        shown = {element for _, element, visible in self.targets if visible}
        for where, element, _ in self.targets:
            if element not in self.element_ids:
                self.add(where, f"names {element!r}, which is not an element of the card")
        for where, element in self.hidden:
            if element is None:
                self.add(where, "starts hidden and has no id, so no button can show it")
            elif element not in shown:
                self.add(where, f"starts hidden, and no button shows {element!r}")

    def root(self, card: object) -> None:
        if not isinstance(card, dict):
            self.add("card", "must be an object")
            return
        for name, value in card.items():
            if name not in ROOT:
                self.add(f"card.{name}", "is not a property of an Adaptive Card that cards use")
        if card.get("type") != "AdaptiveCard":
            self.add("card.type", "must be AdaptiveCard")
        if card.get("$schema") != SCHEMA:
            self.add("card.$schema", f"must be {SCHEMA}")
        if card.get("version") != VERSION:
            self.add("card.version", f"must be {VERSION}: the actions of Power Automate that post a card render no higher version")
        self.text("card.fallbackText", card.get("fallbackText"))
        if not str(card.get("fallbackText", "")).strip():
            self.add("card.fallbackText", "is needed: a client that cannot show the card shows this")
        extra = card.get("msteams")
        if extra is not None and not (isinstance(extra, dict) and set(extra) <= {"width"} and str(extra.get("width", "")).lower() in ENUMS["teams_width"]):
            self.add("card.msteams", "may only set the width to Full")
        body = card.get("body")
        if not isinstance(body, list) or not body:
            self.add("card.body", "must be a list with at least one element")
        else:
            for index, node in enumerate(body):
                self.element(f"card.body[{index}]", node)
        if "actions" in card:
            self.actions("card.actions", card["actions"])
        if self.actions_seen > MAX_ACTIONS:
            self.add("card", f"has {self.actions_seen} actions, and a card has at most {MAX_ACTIONS}")
        self.toggles()
        if len(self.pages) > 1:
            self.add("card", f"carries {len(self.pages)} different pages, and a card is about one request")
        seen: set[str] = set()
        for verb, _ in self.answers:
            if verb in seen:
                self.add("card", f"has two buttons that {verb}")
            seen.add(verb)
        size = size_of(card)
        if size is None:
            self.add("card", "is not JSON")
        elif size > MAX_BYTES:
            self.add("card", f"is {size} bytes, at most {MAX_BYTES}")


def size_of(card: object) -> int | None:
    """The size of the card as the JSON text that goes into a message, in bytes of UTF-8; None when it is not JSON."""
    try:
        return len(json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def check(card: object) -> list[str]:
    """The problems of a card, as plain lines. An empty list means that it passes."""
    state = _Check()
    state.root(card)
    return state.problems
