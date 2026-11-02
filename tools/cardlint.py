#!/usr/bin/env python3
"""Checks for the Adaptive Card templates of the experience design (standard library only).

Cards live in docs/experience/cards/<name>.json, with sample data in cards/data/<name>.json and a
manifest, cards/manifest.json, that says per card which elements must exist and, for every verb, which input ids it accepts,
whether it needs the plan code and what a tap returns. The checks encode the rules of the experience design
(docs/experience/04-messages-and-cards.md): a card says that an AI wrote it, says why the person got it, ends with a way to reach
a person ("Talk to a person", the last button, in the same place on every card) and offers Explain, Challenge and Teach (a claim or a
decision about spend) or Explain alone (the rest); every saving figure carries its price basis; the only link is the owner page
(${pageUrl}); a button sends an opaque id and a verb, never prose; an action that takes no input says associatedInputs none; no urgency
theatre; no en dash or middot between figures; text wraps; images have alternative text; inputs have labels.

Run by tools/check-docs.py (and alone: python tools/cardlint.py [--self-test]).
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "docs" / "experience" / "cards"

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ELEMENTS = {
    "TextBlock", "RichTextBlock", "TextRun", "Container", "ColumnSet", "Column", "FactSet", "Table", "TableRow",
    "TableCell", "ActionSet", "Input.Text", "Input.ChoiceSet", "Input.Toggle", "Image",
    "AdaptiveCard",  # only inside Action.ShowCard
}
ACTIONS = {"Action.Execute", "Action.OpenUrl", "Action.ToggleVisibility", "Action.ShowCard"}
DATA_KEYS = {"verb", "requestId", "option", "scope", "reason", "planCode"}
BASE_VERBS = ("explain", "challenge", "teach")
RETURNS = {"receipt", "card", "answer", "handoff"}
DECISION_VERBS = {"ok", "cancel", "undo", "not-me"}
FOOTER_START = "Written by an AI."
PAGE_URL = "${pageUrl}"
PAGE_URLS = (PAGE_URL, "${$root.pageUrl}")  # the second form is for use inside a $data loop
FIGURE_RANGE = re.compile(r"\d\s*[\u2013\u2014-]\s*\d")  # a dash between two numbers: a screen reader may drop it and merge them
MIDDOT = "\u00b7"
NOTIFICATION_MAX = 120
DARK_PATTERNS = re.compile(
    r"\bURGENT\b|\bact now\b|\bhurry\b|\blast chance\b|\blimited time\b|\bdon't miss\b|\bdon\u2019t miss\b|!{2,}"
    r"|\bonly \d+ (?:hours?|minutes?) left\b|\bwe noticed you (?:have not|haven't)\b", re.I)
LINK = re.compile(r"https?://", re.I)
MD_LINK = re.compile(r"\]\(")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
DEFAULTS = {"max_schema_version": "1.5", "max_bytes": 20000, "max_title_chars": 24, "max_top_actions": 6,
            "max_visible_actions": 8, "max_hidden_actions": 4, "max_options": 2}


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)) or (0,)


def _nodes(obj):
    """Every dict that has a 'type' (card elements, actions, inlines), at any depth."""
    if isinstance(obj, dict):
        if "type" in obj:
            yield obj
        for k, v in obj.items():
            if k != "data":
                yield from _nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _nodes(v)


def _walk(obj, in_show=False, hidden=False, in_fallback=False):
    """(node, inside a ShowCard, inside a hidden container, inside a fallback) for every typed dict."""
    if isinstance(obj, dict):
        if "type" in obj:
            yield obj, in_show, hidden, in_fallback
        child_hidden = hidden or obj.get("isVisible") is False
        for k, v in obj.items():
            if k == "data":
                continue
            if k == "card" and obj.get("type") == "Action.ShowCard":
                yield from _walk(v, True, child_hidden, in_fallback)
            elif k == "fallback":
                yield from _walk(v, in_show, child_hidden, True)
            else:
                yield from _walk(v, in_show, child_hidden, in_fallback)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, in_show, hidden, in_fallback)


def _strings(obj, skip=("$schema",)):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip:
                continue
            yield from _strings(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, skip)
    elif isinstance(obj, str):
        yield obj


def _input_ids(obj) -> list[str]:
    """Ids of the inputs of one card body; the card inside a ShowCard belongs to that action."""
    out: list[str] = []
    if isinstance(obj, dict):
        if str(obj.get("type", "")).startswith("Input.") and "id" in obj:
            out.append(str(obj["id"]))
        for k, v in obj.items():
            if k not in ("card", "data"):
                out += _input_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _input_ids(v)
    return out


def _executes(obj, own: list[str], out: list) -> None:
    """(Action.Execute, ids of the inputs it can gather) for every action outside a fallback.
    An action inside a ShowCard gathers the inputs of its own card and of every parent card."""
    if isinstance(obj, dict):
        t = obj.get("type")
        if t == "Action.Execute":
            out.append((obj, own))
            return
        if t == "Action.ShowCard" and isinstance(obj.get("card"), dict):
            inner = obj["card"]
            _executes(inner.get("body", []) + inner.get("actions", []), own + _input_ids(inner.get("body", [])), out)
            return
        for k, v in obj.items():
            if k not in ("data", "fallback"):
                _executes(v, own, out)
    elif isinstance(obj, list):
        for v in obj:
            _executes(v, own, out)


def check_card(name: str, card: dict, spec: dict, limits: dict, data: dict | None) -> list[str]:
    """Messages for one card template; an empty list means it passes."""
    msgs: list[str] = []
    add = msgs.append
    if card.get("type") != "AdaptiveCard":
        add("type must be AdaptiveCard")
    if card.get("$schema") != SCHEMA:
        add(f"$schema must be {SCHEMA}")
    if _version(str(card.get("version", ""))) > _version(limits["max_schema_version"]) or not card.get("version"):
        add(f"version {card.get('version')!r} must be set and at most {limits['max_schema_version']}")
    if not str(card.get("fallbackText", "")).strip():
        add("fallbackText is required (clients that cannot render a card show it)")
    elif PAGE_URL not in str(card.get("fallbackText", "")):
        add(f"fallbackText must carry {PAGE_URL}: a client below schema 1.5 shows nothing else")
    elif FOOTER_START not in str(card.get("fallbackText", "")):
        add(f"fallbackText must say {FOOTER_START!r}: the AI notice has to survive on a client that shows nothing else")
    size = len(json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > limits["max_bytes"]:
        add(f"template is {size} bytes, the limit is {limits['max_bytes']} (the platform limit leaves no room for data)")
    top_actions = card.get("actions", [])
    if len(top_actions) > limits["max_top_actions"]:
        add(f"{len(top_actions)} top-level actions, at most {limits['max_top_actions']}")

    ids: dict[str, dict] = {}
    verbs: set[str] = set()
    for node in list(_nodes(card.get("body", []))) + list(_nodes(top_actions)):
        t = node.get("type")
        if "id" in node:
            ids[node["id"]] = node
        if t in ELEMENTS:
            if t == "TextBlock":
                if not str(node.get("text", "")).strip():
                    add(f"TextBlock {node.get('id', '?')}: empty text")
                if node.get("wrap") is not True:
                    add(f"TextBlock {node.get('id', node.get('text', '?')[:30])!r}: wrap must be true (no truncated text)")
            elif t == "Image":
                if not str(node.get("altText", "")).strip():
                    add(f"Image {node.get('url', '?')[:30]!r}: altText is required")
            elif t.startswith("Input."):
                if "id" not in node or not str(node.get("label", "")).strip():
                    add(f"{t}: id and label are required")
                if node.get("isRequired") and not node.get("errorMessage"):
                    add(f"{t} {node.get('id', '?')}: a required input needs an errorMessage")
            elif t == "ActionSet" and len(node.get("actions", [])) > limits["max_top_actions"]:
                add(f"ActionSet with {len(node['actions'])} actions, at most {limits['max_top_actions']} (Teams moves the rest into an overflow menu)")
        elif t in ACTIONS or t == "Action.Submit":
            pass
        else:
            add(f"element or action type {t!r} is not in the allowed set")
    walked = list(_walk(card.get("body", []))) + list(_walk(top_actions))
    visible = hidden_count = 0
    root_inputs: list[str] = []
    for node, in_show, hidden, in_fallback in walked:
        t = node.get("type", "")
        if t == "Action.Submit":
            add("Action.Submit is not allowed: it has no token exchange and cannot return a replacement card, "
                "so no change is ever bound to it (the fallback of an Action.Execute is an Action.OpenUrl to the page)")
        elif t == "Action.Execute" and not in_fallback:
            fallback = node.get("fallback")
            if not (isinstance(fallback, dict) and fallback.get("type") == "Action.OpenUrl" and fallback.get("url") in PAGE_URLS):
                add(f"Action.Execute {node.get('title', '?')!r}: the fallback must be an Action.OpenUrl to {PAGE_URL}")
            data_obj = node.get("data", {})
            if node.get("verb") in DECISION_VERBS and not (isinstance(data_obj, dict) and data_obj.get("planCode")):
                add(f"Action.Execute {node.get('title', '?')!r}: the verb {node.get('verb')!r} decides about one plan and must carry planCode")
        elif t == "Action.ToggleVisibility" and not str(node.get("tooltip", "")).strip():
            add(f"Action.ToggleVisibility {node.get('title', '?')!r}: a tooltip is required (screen readers narrate it)")
        if in_fallback:
            continue
        if t.startswith("Action.") and not in_show:
            if hidden:
                hidden_count += 1
            else:
                visible += 1
        if t.startswith("Input.") and not in_show:
            root_inputs.append(str(node.get("id", "?")))
    if visible > limits["max_visible_actions"]:
        add(f"{visible} visible buttons, at most {limits['max_visible_actions']} (one decision, one minute)")
    if hidden_count > limits["max_hidden_actions"]:
        add(f"{hidden_count} buttons behind a toggle, at most {limits['max_hidden_actions']}")
    if root_inputs and not spec.get("rootInputs"):
        add(f"root-level input(s) {root_inputs}: an action inside a ShowCard also sends the inputs of its parent card, "
            "so only cards that say \"rootInputs\" in the manifest may have them")
    for node in list(_nodes(card.get("body", []))) + list(_nodes(top_actions)):
        t = node.get("type")
        if t not in ACTIONS:
            continue
        title = str(node.get("title", "")).strip()
        if not title:
            add(f"{t}: title is required")
        elif len(title) > limits["max_title_chars"]:
            add(f"{t} {title!r}: title is longer than {limits['max_title_chars']} characters")
        elif not re.search(r"[^\W\d_]|\$\{", title):
            add(f"{t} {title!r}: a button needs words, not symbols")
        if t == "Action.OpenUrl":
            if node.get("url") not in PAGE_URLS:
                add(f"Action.OpenUrl {title!r}: the only link a card may carry is {PAGE_URL}")
        elif t in ("Action.Execute", "Action.Submit"):
            data_obj = node.get("data", {})
            verb = node.get("verb") if t == "Action.Execute" else None
            verb = verb or (data_obj.get("verb") if isinstance(data_obj, dict) else None)
            if not verb:
                add(f"{t} {title!r}: a button carries a verb")
            else:
                verbs.add(str(verb))
            if isinstance(data_obj, dict):
                extra = set(data_obj) - DATA_KEYS
                if extra:
                    add(f"{t} {title!r}: data may hold only {sorted(DATA_KEYS)}, found {sorted(extra)}")
        elif t == "Action.ToggleVisibility" and not node.get("targetElements"):
            add(f"Action.ToggleVisibility {title!r}: targetElements is required")
    for key in card:
        if key == "msteams":
            extra = set(card["msteams"]) - {"width"}
            if extra:
                add(f"msteams may set only width, found {sorted(extra)}")

    for s in _strings(card):
        if DARK_PATTERNS.search(s):
            add(f"urgency or pressure wording: {s[:60]!r}")
        if LINK.search(s):
            add(f"a link in the text: {s[:60]!r} (the only link is {PAGE_URL})")
        if MD_LINK.search(s):
            add(f"markdown link syntax in the template: {s[:60]!r}")
        if EMAIL.search(s):
            add(f"an e-mail address in the template: {s[:60]!r}")
        if FIGURE_RANGE.search(s):
            add(f"a dash between two numbers: {s[:60]!r} (write 'to': a screen reader may drop the dash and merge the figures)")
        if MIDDOT in s:
            add(f"a middot in the text: {s[:60]!r} (use a comma or a full stop)")

    for required in spec.get("requires", []) + ["ai-label", "ai-footer"]:
        if required not in ids:
            add(f"required element id {required!r} is missing")
    label = ids.get("ai-label")
    if label is not None:
        text = str(label.get("text", ""))
        if "(AI)" not in text and "${senderName}" not in text:
            add("ai-label must say '(AI)' or bind ${senderName}")
    footer = ids.get("ai-footer")
    if footer is not None and not str(footer.get("text", "")).startswith(FOOTER_START):
        add(f"ai-footer must start with {FOOTER_START!r}")
    kind = spec.get("conversation", "full")
    if kind not in ("full", "light"):
        add(f"manifest conversation must be 'full' or 'light', not {kind!r}")
    contract = spec.get("verbs", {})
    if not isinstance(contract, dict):
        add("manifest verbs must be an object: verb -> {inputs, plan, returns}")
        contract = {}
    for verb in (("explain",) if kind == "light" else BASE_VERBS) + ("human",):
        if verb not in verbs:
            add(f"a button with verb {verb!r} is required")
    for verb in sorted(verbs - set(contract)):
        add(f"verb {verb!r} is on the card but not in the manifest")
    for verb in sorted(set(contract) - verbs):
        add(f"the manifest lists verb {verb!r} that no button on the card carries")
    for verb, entry in contract.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("inputs"), list) or not isinstance(entry.get("plan"), bool) \
                or entry.get("returns") not in RETURNS:
            add(f"manifest verb {verb!r}: needs inputs (a list), plan (true or false) and returns (one of {sorted(RETURNS)})")
    found: list = []
    _executes(card.get("body", []), _input_ids(card.get("body", [])), found)
    _executes(top_actions, _input_ids(card.get("body", [])), found)
    for act, gatherable in found:
        title = act.get("title", "?")
        mode = act.get("associatedInputs")
        entry = contract.get(act.get("verb"), {}) if isinstance(contract, dict) else {}
        if mode not in ("none", "auto"):
            add(f"Action.Execute {title!r}: associatedInputs must be 'none' (no input) or 'auto' (it sends the inputs of its card)")
        elif mode == "auto":
            if not gatherable:
                add(f"Action.Execute {title!r}: associatedInputs 'auto' but there is nothing to send; say 'none'")
            missing = [i for i in gatherable if i not in entry.get("inputs", [])]
            if missing:
                add(f"Action.Execute {title!r}: sends {missing} but the manifest does not list them for verb {act.get('verb')!r}")
        if isinstance(entry, dict) and entry and bool(entry.get("plan")) != bool(isinstance(act.get("data"), dict) and act["data"].get("planCode")):
            add(f"Action.Execute {title!r}: manifest plan flag for verb {act.get('verb')!r} does not match planCode in the action")
    talk = ids.get("talk-to-a-person")
    body = card.get("body", [])
    if talk is None or talk.get("type") != "ActionSet" or not any(
            a.get("verb") == "human" and a.get("title") == "Talk to a person" for a in talk.get("actions", [])):
        add("the footer needs an ActionSet with id 'talk-to-a-person' holding the button 'Talk to a person' (verb human)")
    elif len(body) < 2 or body[-1].get("id") != "ai-footer" or body[-2] is not talk:
        add("'Talk to a person' must be the last button: its ActionSet sits directly above the ai-footer, in the same place on every card")
    shown = ids.get("kind")
    if shown is not None and spec.get("displayTitle") and shown.get("text") != spec["displayTitle"]:
        add(f"manifest displayTitle {spec['displayTitle']!r} must equal the title shown on the card ({shown.get('text')!r})")
    if spec.get("money"):
        for required in ("value", "price-basis", "saving-word"):
            if required not in ids:
                add(f"a card with a money figure needs element id {required!r}")

    if data is not None:
        if data.get("_invented") is not True:
            add("sample data must carry \"_invented\": true")
        if not str(data.get("senderName", "")).endswith("(AI)"):
            add("sample data senderName must end with '(AI)'")
        for key in data:
            if key.lower() in ("recipient", "to", "email", "mail", "url"):
                add(f"sample data key {key!r}: a model never supplies a recipient or a link")
        if not str(data.get("pageUrl", "https://")).startswith("https://"):
            add("sample data pageUrl must be https")
        for key, value in data.items():
            if key.endswith("Label") and isinstance(value, str) and len(value) > limits["max_title_chars"]:
                add(f"sample data {key!r} is bound into a button title and is longer than {limits['max_title_chars']} characters")
        options = data.get("options")
        if isinstance(options, list) and len(options) > limits["max_options"]:
            add(f"sample data lists {len(options)} other options, at most {limits['max_options']} (a further option goes to the page)")
        note = str(data.get("notificationText", "")).strip()
        if not note:
            add("sample data needs notificationText: the one-sentence notification line of the message")
        elif len(note) > NOTIFICATION_MAX:
            add(f"sample data notificationText is {len(note)} characters, at most {NOTIFICATION_MAX}")
        for key, value in data.items():
            if key == "pageUrl":
                continue
            for s in _strings(value):
                if EMAIL.search(s):
                    add(f"sample data holds an e-mail address: {s[:40]!r}")
                if LINK.search(s) or MD_LINK.search(s):
                    add(f"sample data holds a link or markdown link: {s[:40]!r} (bound values are stripped of both)")
                if FIGURE_RANGE.search(s):
                    add(f"sample data has a dash between two numbers: {s[:40]!r} (write 'to')")
                if MIDDOT in s:
                    add(f"sample data has a middot: {s[:40]!r}")
    return msgs


CONTRACT_KEYS = ("who", "repeat", "refused", "response", "words")


def check_contract(manifest: dict) -> list[str]:
    """The rules that hold for every verb must be stated once, in the manifest."""
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        return [f"manifest.json needs a contract object with {list(CONTRACT_KEYS)}: what holds for every verb"]
    return [f"manifest contract {k!r} is missing or empty" for k in CONTRACT_KEYS if not str(contract.get(k, "")).strip()]


def check_scenarios(datas: dict[str, dict]) -> list[tuple[str, str]]:
    """(sample name, message). One example has one request id and its page address; unrelated examples never share an id,
    because a button that sends only an opaque id must not be able to name two different requests."""
    out: list[tuple[str, str]] = []
    by_id: dict[str, set[str]] = {}
    by_scenario: dict[str, set[str]] = {}
    for name, data in datas.items():
        rid, scenario = str(data.get("requestId", "")), str(data.get("_scenario", ""))
        if not scenario:
            out.append((name, "sample data needs \"_scenario\": the example it belongs to"))
        if not rid:
            out.append((name, "sample data needs a requestId"))
            continue
        if not str(data.get("pageUrl", "")).endswith("/" + rid):
            out.append((name, f"pageUrl must end with the request id {rid!r}"))
        by_id.setdefault(rid, set()).add(scenario)
        by_scenario.setdefault(scenario, set()).add(rid)
    for name, data in datas.items():
        rid, scenario = str(data.get("requestId", "")), str(data.get("_scenario", ""))
        if len(by_id.get(rid, ())) > 1:
            out.append((name, f"request id {rid!r} is shared by unrelated examples {sorted(by_id[rid])}"))
        if scenario and len(by_scenario.get(scenario, ())) > 1:
            out.append((name, f"example {scenario!r} has more than one request id {sorted(by_scenario[scenario])}"))
    return out


def check(cards_dir: Path = CARDS) -> list[tuple[Path, str]]:
    """(file, message) for every problem in the card templates under cards_dir."""
    out: list[tuple[Path, str]] = []
    manifest_path = cards_dir / "manifest.json"
    if not cards_dir.exists():
        return out
    if not manifest_path.exists():
        return [(cards_dir, "manifest.json is missing")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [(manifest_path, f"manifest.json is not valid JSON: {e}")]
    limits = {**DEFAULTS, **manifest.get("limits", {})}
    out += [(manifest_path, msg) for msg in check_contract(manifest)]
    listed = set()
    datas: dict[str, dict] = {}
    for cid, spec in manifest.get("cards", {}).items():
        path = cards_dir / spec["file"]
        listed.add(path.name)
        if not path.exists():
            out.append((manifest_path, f"{cid}: {spec['file']} does not exist"))
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            out.append((path, f"not valid JSON: {e}"))
            continue
        data_path = cards_dir / "data" / path.name
        data = None
        if data_path.exists():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                out.append((data_path, f"sample data is not valid JSON: {e}"))
                continue
            datas[cid] = data
        else:
            out.append((path, f"{cid}: sample data cards/data/{path.name} is missing"))
        for msg in check_card(cid, card, spec, limits, data):
            out.append((path, f"{cid}: {msg}"))
    for name, msg in check_scenarios(datas):
        out.append((cards_dir / "data" / manifest["cards"][name]["file"], f"{name}: {msg}"))
    for path in sorted(cards_dir.glob("*.json")):
        if path.name != "manifest.json" and path.name not in listed:
            out.append((path, "not listed in manifest.json"))
    return out


def _button(verb, title="Explain", inputs=False, **extra):
    data = {"requestId": "${requestId}"}
    data.update(extra)
    return {"type": "Action.Execute", "title": title, "verb": verb, "data": data,
            "associatedInputs": "auto" if inputs else "none",
            "fallback": {"type": "Action.OpenUrl", "title": "Open on the page", "url": PAGE_URL}}


def _sample() -> tuple[dict, dict, dict, dict]:
    btn = _button
    card = {
        "type": "AdaptiveCard", "$schema": SCHEMA, "version": "1.5",
        "fallbackText": "A recommendation from Cost in Action (AI). Open it on the page: ${pageUrl} Written by an AI.",
        "body": [
            {"type": "TextBlock", "id": "ai-label", "text": "${senderName}", "wrap": True},
            {"type": "TextBlock", "id": "headline", "text": "${headline}", "wrap": True},
            {"type": "TextBlock", "id": "value", "text": "${value}", "wrap": True},
            {"type": "TextBlock", "id": "price-basis", "text": "${priceBasis}", "wrap": True},
            {"type": "TextBlock", "id": "saving-word", "text": "${savingWord}", "wrap": True},
            {"type": "ActionSet", "id": "conversation", "actions": [btn("explain"), btn("challenge", "Challenge"), btn("teach", "Teach")]},
            {"type": "TextBlock", "id": "why-you-get-this", "text": "Why you are getting this: ${whyYouGetThis}", "wrap": True},
            {"type": "ActionSet", "id": "talk-to-a-person", "actions": [btn("human", "Talk to a person")]},
            {"type": "TextBlock", "id": "ai-footer", "text": "Written by an AI. Figures are computed by tools, not guessed by the AI.", "wrap": True},
        ],
    }
    contract = {"explain": {"inputs": [], "plan": False, "returns": "answer"}, "challenge": {"inputs": [], "plan": False, "returns": "answer"},
                "teach": {"inputs": [], "plan": False, "returns": "answer"}, "human": {"inputs": [], "plan": False, "returns": "handoff"}}
    spec = {"file": "x.json", "money": True, "requires": ["headline", "why-you-get-this"], "verbs": contract}
    limits = dict(DEFAULTS)
    data = {"_invented": True, "senderName": "Cost in Action (AI)", "pageUrl": "https://costinaction.example/ok/abc",
            "notificationText": "Switch off the QA environment at night?"}
    return card, spec, limits, data


def self_test() -> int:
    card, spec, limits, data = _sample()
    assert check_card("t", card, spec, limits, data) == [], check_card("t", card, spec, limits, data)

    def broken(mutate, needle, **kw):
        c = copy.deepcopy(card)
        d = copy.deepcopy(data)
        s = copy.deepcopy(spec)
        mutate(c, d, s)
        found = check_card("t", c, s, limits, d)
        assert any(needle in m for m in found), f"missed: {needle!r} in {found}"

    button = _button

    broken(lambda c, d, s: c["body"][1].pop("wrap"), "wrap must be true")
    broken(lambda c, d, s: c["body"].append({"type": "Image", "url": "x"}), "altText is required")
    broken(lambda c, d, s: c["body"].append({"type": "Input.Text", "id": "a"}), "id and label are required")
    broken(lambda c, d, s: c["body"].append({"type": "Input.Text", "id": "a", "label": "A", "isRequired": True}), "errorMessage")
    broken(lambda c, d, s: (s.update({"rootInputs": False}), c["body"].append({"type": "Input.Text", "id": "a", "label": "A"})), "root-level input")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [
        {"type": "Action.OpenUrl", "title": "Open", "url": "https://evil.example"}]}), "only link")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [
        {"type": "Action.Http", "title": "Go", "url": "x"}]}), "not in the allowed set")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [
        {"type": "Action.Submit", "title": "Go", "data": {"verb": "explain"}}]}), "Action.Submit is not allowed")
    broken(lambda c, d, s: c["body"][5]["actions"][0].pop("fallback"), "fallback must be an Action.OpenUrl")
    broken(lambda c, d, s: c["body"][5]["actions"][0].update({"fallback": {"type": "Action.OpenUrl", "title": "x", "url": "https://x.example"}}), "fallback must be an Action.OpenUrl")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [button("ok", "OK")]}), "must carry planCode")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [
        {"type": "Action.ToggleVisibility", "title": "Details", "targetElements": ["x"]}]}), "tooltip is required")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [button("explain", "B%d" % i) for i in range(6)]}), "visible buttons")
    broken(lambda c, d, s: (c["body"].append({"type": "Container", "isVisible": False, "items": [
        {"type": "ActionSet", "actions": [button("fewer", "F%d" % i) for i in range(5)]}]})), "behind a toggle")
    broken(lambda c, d, s: c["body"][5]["actions"].pop(2), "verb 'teach' is required")
    broken(lambda c, d, s: c["body"][7]["actions"].pop(), "verb 'human' is required")
    broken(lambda c, d, s: c["body"].pop(7), "'talk-to-a-person'")
    broken(lambda c, d, s: c["body"].insert(8, {"type": "ActionSet", "actions": [button("explain", "Again")]}), "must be the last button")
    broken(lambda c, d, s: (s.update({"conversation": "light"}), c["body"][5]["actions"].pop(0)), "verb 'explain' is required")
    broken(lambda c, d, s: c["body"].pop(6), "'why-you-get-this'")
    broken(lambda c, d, s: c["body"][5]["actions"][0]["data"].update({"text": "free prose"}), "data may hold only")
    broken(lambda c, d, s: c["body"][1].update({"text": "ACT NOW, hurry"}), "urgency")
    broken(lambda c, d, s: c["body"][1].update({"text": "see https://x.example"}), "a link in the text")
    broken(lambda c, d, s: c["body"][1].update({"text": "see [this](x)"}), "markdown link syntax")
    broken(lambda c, d, s: c["body"][1].update({"text": "write to a@b.example"}), "e-mail address")
    broken(lambda c, d, s: c["body"].pop(4), "'saving-word'")
    broken(lambda c, d, s: c["body"][-1].update({"text": "no label"}), "ai-footer must start")
    broken(lambda c, d, s: c.update({"version": "1.6"}), "must be set and at most")
    broken(lambda c, d, s: c.pop("fallbackText"), "fallbackText")
    broken(lambda c, d, s: c.update({"fallbackText": "A recommendation."}), "fallbackText must carry")
    broken(lambda c, d, s: c["body"].append({"type": "Carousel"}), "not in the allowed set")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [
        {"type": "Action.Execute", "title": f"B{i}", "verb": "explain", "data": {"requestId": "x"}} for i in range(7)]}), "at most 6")
    broken(lambda c, d, s: c["body"].append({"type": "ActionSet", "actions": [button("explain", "A title that is too long for Teams")]}), "title is longer")
    broken(lambda c, d, s: c.update({"msteams": {"entities": []}}), "msteams may set only width")
    broken(lambda c, d, s: d.update({"_invented": False}), "_invented")
    broken(lambda c, d, s: d.update({"senderName": "Cost in Action"}), "senderName must end")
    broken(lambda c, d, s: d.update({"recipient": "x"}), "never supplies a recipient")
    broken(lambda c, d, s: d.update({"okLabel": "A label that is far too long to be a button"}), "button title")
    broken(lambda c, d, s: d.update({"options": [{}, {}, {}]}), "other options")
    broken(lambda c, d, s: d.update({"why": "see [this](https://x.example)"}), "link or markdown link")
    broken(lambda c, d, s: c["body"].append({"type": "TextBlock", "text": "x" * 21000, "wrap": True}), "bytes")

    # Regression tests: inputs and actions inside a top-level ShowCard and a top-level Action.Http were once unchecked.
    broken(lambda c, d, s: c.setdefault("actions", []).append({"type": "Action.ShowCard", "title": "More", "card": {
        "type": "AdaptiveCard", "body": [{"type": "Input.Text", "id": "a", "isRequired": True}]}}), "id and label are required")
    broken(lambda c, d, s: c.setdefault("actions", []).append({"type": "Action.Http", "title": "Go", "url": "x"}), "not in the allowed set")

    # Titles in any script pass; symbols alone do not.
    for title in ("\u4fdd\u5b58", "\u062d\u0641\u0638", "Opslaan"):
        ok = copy.deepcopy(card)
        ok["body"][5]["actions"][0]["title"] = title
        assert not any("needs words" in m for m in check_card("t", ok, spec, limits, data)), f"rejected the title {title!r}"
    broken(lambda c, d, s: c["body"][5]["actions"][0].update({"title": "\u2192\u2192"}), "needs words")

    # Figures: no dash between numbers (a screen reader may drop it), no middot.
    broken(lambda c, d, s: c["body"][1].update({"text": "Range \u20ac620\u2013760"}), "dash between two numbers")
    broken(lambda c, d, s: c["body"][1].update({"text": "Open 07:30-19:30"}), "dash between two numbers")
    broken(lambda c, d, s: c["body"][1].update({"text": "For you \u00b7 14 resources"}), "middot")
    broken(lambda c, d, s: d.update({"range": "Range \u20ac620\u2013760"}), "dash between two numbers")
    broken(lambda c, d, s: d.update({"scope": "For you \u00b7 14 resources"}), "middot")
    broken(lambda c, d, s: d.pop("notificationText"), "notificationText")

    # The action contract: inputs, the plan flag and the manifest agree with the card.
    broken(lambda c, d, s: c["body"][5]["actions"][0].pop("associatedInputs"), "associatedInputs must be")
    broken(lambda c, d, s: c["body"][5]["actions"][0].update({"associatedInputs": "auto"}), "nothing to send")
    broken(lambda c, d, s: c["body"][5]["actions"].append(button("zzz", "Other")), "not in the manifest")
    broken(lambda c, d, s: s["verbs"].update({"zzz": {"inputs": [], "plan": False, "returns": "receipt"}}), "no button on the card carries")
    broken(lambda c, d, s: s["verbs"]["explain"].update({"returns": "nothing"}), "needs inputs")
    broken(lambda c, d, s: s["verbs"]["explain"].update({"plan": True}), "plan flag")
    broken(lambda c, d, s: (c["body"].insert(0, {"type": "Input.Text", "id": "free", "label": "Free"}), s.update({"rootInputs": True}),
                            c["body"][6]["actions"][0].update({"associatedInputs": "auto"})), "sends ['free'] but the manifest does not list")
    broken(lambda c, d, s: (c["body"].insert(0, {"type": "TextBlock", "id": "kind", "text": "Hello", "wrap": True}), s.update({"displayTitle": "Recommendation"})), "displayTitle")
    broken(lambda c, d, s: c.update({"fallbackText": "A recommendation. Open it on the page: ${pageUrl}"}), "fallbackText must say")

    # An action inside a ShowCard also sends the inputs of its parent card, so the manifest must list them too.
    def under_a_show_card(c, d, s):
        c["body"].insert(0, {"type": "Input.Text", "id": "free", "label": "Free"})
        s["rootInputs"] = True
        c["body"][6]["actions"][0] = {"type": "Action.ShowCard", "title": "Explain", "card": {
            "type": "AdaptiveCard", "body": [{"type": "Input.Text", "id": "level", "label": "Level"}],
            "actions": [button("explain", "Send", inputs=True)]}}
        s["verbs"]["explain"]["inputs"] = ["level"]
    broken(under_a_show_card, "sends ['free'] but the manifest does not list")
    listed = copy.deepcopy(card)
    listed_spec = copy.deepcopy(spec)
    under_a_show_card(listed, data, listed_spec)
    listed_spec["verbs"]["explain"]["inputs"] = ["level", "free"]
    assert check_card("t", listed, listed_spec, limits, data) == [], check_card("t", listed, listed_spec, limits, data)

    # One example, one request id; unrelated examples never share one.
    def sample(rid, scenario, page=None):
        return {"requestId": rid, "pageUrl": page or f"https://x.example/ok/{rid}", "_scenario": scenario}
    assert check_scenarios({"a": sample("r_1", "E1"), "b": sample("r_1", "E1"), "c": sample("r_2", "E4")}) == []
    assert any("shared by unrelated" in m for _, m in check_scenarios({"a": sample("r_1", "E1"), "b": sample("r_1", "E6")}))
    assert any("more than one request id" in m for _, m in check_scenarios({"a": sample("r_1", "E1"), "b": sample("r_2", "E1")}))
    assert any("pageUrl must end" in m for _, m in check_scenarios({"a": sample("r_1", "E1", "https://x.example/ok/r_9")}))
    assert any("_scenario" in m for _, m in check_scenarios({"a": {"requestId": "r_1", "pageUrl": "https://x.example/ok/r_1"}}))

    # The rules for every verb are stated once, in the manifest.
    assert check_contract({}) and check_contract({"contract": {"who": "x"}})
    assert check_contract({"contract": {k: "x" for k in CONTRACT_KEYS}}) == []
    print("cardlint self-test OK")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    problems = check()
    for path, msg in problems:
        print(f"{path.relative_to(ROOT).as_posix()}: ERROR: {msg}")
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
