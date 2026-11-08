"""A structural check of an Adaptive Card of schema 1.5, written with the standard library (cards.py makes every card of the bot, and this checks it).

The renderers of the repository's card tooling (tools/render-cards) need node packages that cannot be installed on the machines that build this repository, so the card is checked
here against what the public schema (https://adaptivecards.microsoft.com/schemas/adaptive-card.json, read on 2026-11-08) says about the elements and actions that cards.py uses and
against the rules of this project that a machine can check. The check is deliberately narrower than the schema: an element or an action that cards.py does not use is an error
(a card with an Action.Submit, an image, a table or a link in a text is a mistake here), a property that the schema does not list for its element is an error (a typo would be
ignored by a renderer and be seen by nobody), and the size, the links, the identifiers and the characters of every text are held to what the card needs.

`check(card)` returns the problems as plain lines with the path of each; an empty list means that the card passes. cards.py checks the card that it made before it hands it on, and
sends nothing when a problem is found.
"""
from __future__ import annotations

import json
import re
import unicodedata

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
VERSION = "1.5"
MAX_BYTES = 20000  # the platform's limit for a message is 100 KB (Learn, "Teams limits"); a card of this repository stays far below it
MAX_ACTIONS_IN_A_SET = 6  # Teams shows six actions and puts the rest in an overflow menu
HIDDEN = ("Cc", "Cf", "Cs", "Co", "Cn")

ENUMS = {
    "color": {"default", "dark", "light", "accent", "good", "warning", "attention"},
    "size": {"default", "small", "medium", "large", "extralarge"},
    "weight": {"default", "lighter", "bolder"},
    "spacing": {"default", "none", "small", "medium", "large", "extralarge", "padding"},
    "style_container": {"default", "emphasis", "good", "attention", "warning", "accent"},
    "style_text": {"default", "heading"},
    "style_action": {"default", "positive", "destructive"},
    "associatedinputs": {"auto", "none"},
    "mode": {"primary", "secondary"},
    "horizontalalignment": {"left", "center", "right"},
    "teams_width": {"full"},
}
COMMON = {"id": "str", "isVisible": "bool", "separator": "bool", "spacing": "spacing", "height": "height", "fallback": "any", "requires": "dict"}
ELEMENTS = {
    "TextBlock": {**COMMON, "text": "str", "color": "color", "isSubtle": "bool", "maxLines": "int", "size": "size", "weight": "weight", "wrap": "bool", "style": "style_text",
                  "horizontalAlignment": "horizontalalignment", "fontType": "any"},
    "ColumnSet": {**COMMON, "columns": "columns", "style": "style_container", "bleed": "bool", "minHeight": "str", "horizontalAlignment": "horizontalalignment"},
    "Column": {**COMMON, "items": "items", "width": "width", "style": "style_container", "bleed": "bool", "minHeight": "str", "verticalContentAlignment": "any"},
    "Container": {**COMMON, "items": "items", "style": "style_container", "bleed": "bool", "minHeight": "str", "verticalContentAlignment": "any"},
    "FactSet": {**COMMON, "facts": "facts"},
    "ActionSet": {**COMMON, "actions": "actions"},
    "Input.Text": {**COMMON, "label": "str", "isRequired": "bool", "errorMessage": "str", "placeholder": "str", "value": "str", "isMultiline": "bool", "maxLength": "int",
                   "style": "any", "regex": "str"},
}
ACTION_COMMON = {"id": "str", "title": "str", "style": "style_action", "tooltip": "str", "isEnabled": "bool", "mode": "mode", "fallback": "any", "requires": "dict"}
ACTIONS = {
    "Action.Execute": {**ACTION_COMMON, "verb": "str", "data": "data", "associatedInputs": "associatedinputs"},
    "Action.OpenUrl": {**ACTION_COMMON, "url": "str"},
}
ROOT = {"type", "$schema", "version", "fallbackText", "body", "actions", "msteams", "lang", "speak"}
REQUIRED = {"TextBlock": {"text"}, "FactSet": {"facts"}, "ActionSet": {"actions"}, "Container": {"items"}, "Input.Text": {"id"}, "Action.OpenUrl": {"url"}}
HTTPS = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%/-]*)?")


def _kind(value: object) -> str:
    return "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "float" if isinstance(value, float) else type(value).__name__


class _Check:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.ids: set[str] = set()
        self.links: set[str] = set()

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
        elif rule == "data":
            if not isinstance(value, (dict, str)):
                self.add(path, "must be an object or a string")
            elif isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(item, (str, int, bool)) or isinstance(item, float):
                        self.add(f"{path}.{key}", "must be a string, a whole number or a boolean")
                    elif isinstance(item, str):
                        self.text(f"{path}.{key}", item)

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
                self.value(f"{path}.{name}", "style" if name == "style" and kind != "TextBlock" else spec[name], value, kind)
        for name in REQUIRED.get(kind, ()):
            if name not in node:
                self.add(path, f"{kind} needs {name}")
        if kind == "TextBlock":
            if node.get("wrap") is not True:
                self.add(path, "wrap must be true, so that no text is cut")
            if isinstance(node.get("text"), str) and not node["text"].strip():
                self.add(path, "a TextBlock has no text")
        if kind == "Input.Text":
            if node.get("isRequired") is True and not node.get("errorMessage"):
                self.add(path, "a required input needs an errorMessage")
            if not str(node.get("label", "")).strip():
                self.add(path, "an input needs a label")
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
        if len(value) > MAX_ACTIONS_IN_A_SET:
            self.add(path, f"{len(value)} actions, at most {MAX_ACTIONS_IN_A_SET} (Teams puts the rest in an overflow menu)")
        for index, node in enumerate(value):
            self.action(f"{path}[{index}]", node)

    def action(self, path: str, node: object, fallback: bool = False) -> None:
        if not isinstance(node, dict):
            self.add(path, "must be an object")
            return
        kind = node.get("type")
        if kind not in ACTIONS:
            self.add(path, f"the action type {kind!r} is not one that cards use (no Action.Submit: it cannot return a card)")
            return
        spec = ACTIONS[kind]
        for name, value in node.items():
            if name == "type":
                continue
            if name not in spec:
                self.add(f"{path}.{name}", f"is not a property of {kind}")
            elif name == "fallback":
                if fallback:
                    self.add(f"{path}.fallback", "a fallback has no fallback")
                elif kind != "Action.Execute":
                    self.add(f"{path}.fallback", "only an Action.Execute has a fallback")
                else:
                    self.action(f"{path}.fallback", value, fallback=True)
            elif name == "requires":
                self.add(f"{path}.requires", "an action that needs a feature check is not used")
            elif name == "id":
                self.text(f"{path}.id", value)
                if isinstance(value, str):
                    if value in self.ids:
                        self.add(f"{path}.id", f"the id {value!r} is used twice")
                    self.ids.add(value)
            else:
                self.value(f"{path}.{name}", spec[name], value, kind)
        if not str(node.get("title", "")).strip():
            self.add(path, "an action has a title")
        for name in REQUIRED.get(kind, ()):
            if name not in node:
                self.add(path, f"{kind} needs {name}")
        if kind == "Action.OpenUrl":
            url = node.get("url")
            if not isinstance(url, str) or not HTTPS.fullmatch(url):
                self.add(f"{path}.url", "must be an https address")
            else:
                self.links.add(url)
        if kind == "Action.Execute" and not fallback:
            if not str(node.get("verb", "")).strip():
                self.add(path, "an Action.Execute has a verb")
            if str(node.get("associatedInputs", "")).lower() not in ENUMS["associatedinputs"]:
                self.add(path, "associatedInputs says auto or none: an action that takes no input says so")
            fall = node.get("fallback")
            if not isinstance(fall, dict) or fall.get("type") != "Action.OpenUrl":
                self.add(path, "an Action.Execute has an Action.OpenUrl as its fallback, for the clients that cannot run it")

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
            self.add("card.version", f"must be {VERSION}: Action.Execute needs it, and a higher one is not shown by every Teams client")
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
        if len(self.links) > 1:
            self.add("card", f"carries {len(self.links)} different links, and a card has one: the page of its request")
        try:
            size = len(json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError):
            self.add("card", "is not JSON")
        else:
            if size > MAX_BYTES:
                self.add("card", f"is {size} bytes, at most {MAX_BYTES}")


def check(card: object) -> list[str]:
    """The problems of a card, as plain lines. An empty list means that it passes."""
    state = _Check()
    state.root(card)
    return state.problems
