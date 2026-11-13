#!/usr/bin/env python3
"""Builds the Teams app package of the Meternaut bot, a zip file with the manifest and two icons (standard library only).

    python tools/teams-app.py build [--out <folder>] [--valid-domain <host>]... [--env-file <file>]
    python tools/teams-app.py check <package.zip>

The Teams bot (docs/proposals/20-teams-cards-through-a-bot.md) is a notification-only bot: one bot in the personal scope that sends cards and receives nothing. Teams needs an app package to show the app to people,
and a Teams administrator uploads it to the organisation's app catalog (Teams admin center, Teams apps, Manage apps, Upload new app). This tool BUILDS the file and installs nothing: it calls no service and uploads
nothing.

build  Writes meternaut-teams-app.zip to a folder OUTSIDE the repository (default: meternaut-teams-app in the system's temporary folder, or --out). The package holds manifest.json (schema version 1.30, the
       latest that Microsoft Learn lists on 2026-11-13: https://learn.microsoft.com/microsoft-365/extensibility/schema/), color.png (192x192) and outline.png (32x32), both drawn here with the standard library.
       The same bytes come out every time. The bot's client id (the app registration Meternaut Teams, which tools/entra-setup.py teams-bot makes) is read from the environment variable TEAMS_BOT_APP_ID or, when
       that is not set, from the file local/hub-local.env of the repository, which git ignores (a line TEAMS_BOT_APP_ID=<client id>; no other line is read), or from the file that --env-file names. The host that
       the buttons of a card open goes into validDomains: Learn says that Teams shows "URL may lead to untrusted content" for an Action.OpenUrl whose domain is not listed. It is read from --valid-domain (repeat it)
       or from CONSOLE_HOST_NAME in the same places. Both values belong to the estate: the package is built on the machine of the person who uploads it, nothing of it is committed or printed, and the tool prints the
       path of the zip and its size and nothing else. It refuses to write a package that fails `check`, and a folder inside the repository.
check  Validates a package against the rules of the manifest that can be checked offline: the required fields, the lengths, the shapes of the GUIDs, https addresses, valid domains, no secret, one personal bot
       that is notification only, and two PNG icons of the right size. It prints a line for each rule that fails and nothing else.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.30"
SCHEMA_URL = f"https://developer.microsoft.com/json-schemas/teams/v{SCHEMA_VERSION}/MicrosoftTeams.schema.json"
# The id of the Teams app, generated once and never changed: Teams treats a package with another id as another app, and an update of the package (a higher version) keeps this one. A deep link to the app is
# https://teams.microsoft.com/l/app/<this id>.
TEAMS_APP_ID = "f3a9efc4-ae3e-4d9a-a71c-b11d0f2d00f5"
APP_VERSION = "1.0.0"
ACCENT_COLOR = "#0F6CBD"
REPOSITORY_URL = "https://github.com/tinodo/meternaut"
PRIVACY_URL = f"{REPOSITORY_URL}/blob/main/docs/proposals/20-teams-cards-through-a-bot.md#what-the-app-sends-and-keeps"
TERMS_URL = f"{REPOSITORY_URL}/blob/main/LICENSE"
NAME_SHORT = "Meternaut"
NAME_FULL = "Meternaut cost-saving cards"
DESCRIPTION_SHORT = "Azure cost-saving advice, written by AI. A person approves every change."
DESCRIPTION_FULL = ("AI-written recommendations for Azure cost savings. A person approves every change. Meternaut sends you one card for each recommendation that needs your decision. "
                    "A card says what is asked, what it gives, how sure it is, what happens if you say yes and whose rights it uses, and its buttons open a page of the Meternaut function app, where you decide. "
                    "The bot only sends cards: it reads nothing that you write, it asks for no permission in your tenant, and it holds no secret.")
PACKAGE_NAME = "meternaut-teams-app.zip"
KEYS_READ = ("TEAMS_BOT_APP_ID", "CONSOLE_HOST_NAME")
LOCAL_ENV_FILE = ROOT / "local" / "hub-local.env"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DOMAIN = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
SECRET_SHAPES = (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}"), re.compile(r"(?i)\b(secret|password|passwd|pwd|api[_-]?key|client_?secret)\s*[:=]\s*\S+"),
                 re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), re.compile(r"[A-Za-z0-9+/=_-]{40,}"))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ICON_SIZES = {"color.png": 192, "outline.png": 32}
MAX_ICON_BYTES = 100_000
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


class Problem(Exception):
    """Something the person who runs the tool can fix; printed without a trace."""


# ---- the icons ----------------------------------------------------------------------------------------------------------------------------------

def png(width: int, height: int, pixel) -> bytes:
    """A PNG of 8-bit RGBA that pixel(x, y) -> (r, g, b, a) draws, with the filter 0 on every row, so that the bytes are the same every time."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixel(x, y))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def inside(polygon: list[tuple[float, float]], x: float, y: float) -> bool:
    """The even-odd rule for a point and a polygon."""
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


# The letter M, as one polygon on a unit square (a thick stroke: two stems and a V between them).
LETTER = [(0.0, 1.0), (0.0, 0.0), (0.22, 0.0), (0.5, 0.52), (0.78, 0.0), (1.0, 0.0), (1.0, 1.0), (0.80, 1.0), (0.80, 0.42), (0.55, 0.86), (0.45, 0.86), (0.20, 0.42), (0.20, 1.0)]


def coverage(polygon: list[tuple[float, float]], x: int, y: int, size: int, box: tuple[float, float, float, float], samples: int = 4) -> float:
    """How much of a pixel the polygon covers (a grid of samples a side), the polygon being scaled into the box (left, top, width, height) of the image."""
    left, top, width, height = box
    hits = 0
    for i in range(samples):
        for j in range(samples):
            u = (x + (i + 0.5) / samples - left) / width
            v = (y + (j + 0.5) / samples - top) / height
            if 0 <= u <= 1 and 0 <= v <= 1 and inside(polygon, u, v):
                hits += 1
    return hits / (samples * samples)


def color_icon() -> bytes:
    """192x192: a rounded square in the accent colour with a white M, which Teams shows on the app tile. Simple and flat."""
    size, radius = 192, 36
    accent = tuple(int(ACCENT_COLOR[i:i + 2], 16) for i in (1, 3, 5))

    def pixel(x, y):
        dx = max(radius - x - 0.5, 0, x + 0.5 - (size - radius))
        dy = max(radius - y - 0.5, 0, y + 0.5 - (size - radius))
        if dx * dx + dy * dy > radius * radius:
            return (0, 0, 0, 0)
        white = coverage(LETTER, x, y, size, (48, 52, 96, 88))
        return tuple(round(a + (255 - a) * white) for a in accent) + (255,)

    return png(size, size, pixel)


def outline_icon() -> bytes:
    """32x32: the same M as a white stroke on a transparent background, with the rounded square drawn as an outline of two pixels, which is what Teams asks of the outline icon (white or transparent only)."""
    size = 32

    def pixel(x, y):
        edge = min(x, y, size - 1 - x, size - 1 - y)
        ring = 1.0 if edge < 2 and not (edge == 0 and (x in (0, size - 1)) and (y in (0, size - 1))) else 0.0
        white = max(ring, coverage(LETTER, x, y, size, (8, 9, 16, 14)))
        return (255, 255, 255, round(255 * white))

    return png(size, size, pixel)


# ---- the manifest -------------------------------------------------------------------------------------------------------------------------------

def manifest(bot_id: str, valid_domains: list[str]) -> dict:
    """The manifest of schema 1.30. One bot, in the personal scope, notification only, that handles no files: it sends cards and receives nothing."""
    document = {
        "$schema": SCHEMA_URL,
        "manifestVersion": SCHEMA_VERSION,
        "version": APP_VERSION,
        "id": TEAMS_APP_ID,
        "developer": {"name": "Meternaut", "websiteUrl": REPOSITORY_URL, "privacyUrl": PRIVACY_URL, "termsOfUseUrl": TERMS_URL},
        "name": {"short": NAME_SHORT, "full": NAME_FULL},
        "description": {"short": DESCRIPTION_SHORT, "full": DESCRIPTION_FULL},
        "icons": {"color": "color.png", "outline": "outline.png"},
        "accentColor": ACCENT_COLOR,
        "bots": [{"botId": bot_id, "scopes": ["personal"], "isNotificationOnly": True, "supportsFiles": False}],
    }
    if valid_domains:
        document["validDomains"] = valid_domains
    return document


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def check_manifest(document: dict, files: dict[str, bytes] | None = None) -> list[str]:
    """What is wrong with a manifest, by the rules that Learn gives for schema 1.30 and that can be checked offline. Empty when nothing is."""
    problems: list[str] = []

    def need(condition: bool, text: str) -> None:
        if not condition:
            problems.append(text)

    need(document.get("manifestVersion") == SCHEMA_VERSION, f"manifestVersion is {SCHEMA_VERSION}")
    need(isinstance(document.get("version"), str) and bool(SEMVER.match(document["version"])) and len(document["version"]) <= 256, "version is semver: 1.0.0")
    need(isinstance(document.get("id"), str) and bool(GUID.match(document["id"])), "id is a GUID")
    developer = document.get("developer") or {}
    need(isinstance(developer.get("name"), str) and 1 <= len(developer["name"]) <= 32, "developer.name is 1 to 32 characters")
    for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
        value = developer.get(key)
        need(isinstance(value, str) and value.startswith("https://") and len(value) <= 2048 and " " not in value, f"developer.{key} is an https address of at most 2048 characters")
    name = document.get("name") or {}
    need(isinstance(name.get("short"), str) and 1 <= len(name["short"]) <= 30, "name.short is 1 to 30 characters")
    need(isinstance(name.get("full"), str) and 1 <= len(name["full"]) <= 100, "name.full is 1 to 100 characters")
    need(name.get("short") != name.get("full"), "name.short and name.full are different")
    description = document.get("description") or {}
    need(isinstance(description.get("short"), str) and 1 <= len(description["short"]) <= 80, "description.short is 1 to 80 characters")
    need(isinstance(description.get("full"), str) and 1 <= len(description["full"]) <= 4000, "description.full is 1 to 4000 characters")
    need(description.get("short") != description.get("full") and str(description.get("short")) not in str(description.get("full")), "description.short is not repeated in description.full")
    need(document.get("icons") == {"color": "color.png", "outline": "outline.png"}, "icons name color.png and outline.png")
    need(isinstance(document.get("accentColor"), str) and bool(COLOR.match(document["accentColor"])), "accentColor is a colour such as #0F6CBD")
    bots = document.get("bots")
    need(isinstance(bots, list) and len(bots) == 1, "there is one bot")
    if isinstance(bots, list) and bots:
        bot = bots[0]
        need(isinstance(bot.get("botId"), str) and bool(GUID.match(bot["botId"])), "bots[0].botId is the client id of the app registration (a GUID)")
        need(bot.get("scopes") == ["personal"], "the bot's scope is personal and nothing else")
        need(bot.get("isNotificationOnly") is True, "the bot is notification only")
        need(bot.get("supportsFiles") is False, "the bot does not support files")
        need(not {"supportsCalling", "supportsVideo", "commandLists", "configuration"} & set(bot), "the bot has no calling, no commands and no configuration")
    domains = document.get("validDomains", [])
    need(isinstance(domains, list) and len(domains) <= 16 and all(isinstance(d, str) and bool(DOMAIN.match(d)) and not d.startswith("*") for d in domains),
         "validDomains are host names, at most 16, with no scheme, no path and no wildcard")
    need(not {"webApplicationInfo", "staticTabs", "configurableTabs", "composeExtensions", "permissions", "authorization"} & set(document),
         "the app has no tab, no messaging extension, no sign-in and no permission of its own")
    for text in strings({k: v for k, v in document.items() if k not in ("$schema", "id", "bots")}):
        need(text.startswith("https://") or not any(shape.search(text) for shape in SECRET_SHAPES), "no value looks like a secret or a token")
    if files is not None:
        need(set(files) == {"manifest.json", "color.png", "outline.png"}, "the package holds manifest.json, color.png and outline.png and nothing else")
        for file_name, side in ICON_SIZES.items():
            data = files.get(file_name, b"")
            ok = data.startswith(PNG_SIGNATURE) and len(data) <= MAX_ICON_BYTES and len(data) >= 24 and struct.unpack(">II", data[16:24]) == (side, side)
            need(ok, f"{file_name} is a PNG of {side}x{side} pixels, at most 100 KB")
    return sorted(set(problems))


# ---- reading the estate's values ----------------------------------------------------------------------------------------------------------------

def read_env_file(path: Path) -> dict[str, str]:
    """The two keys that the tool needs, from a file of NAME=VALUE lines, and no other line: a comment, another name or a malformed line is skipped and never kept."""
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise Problem(f"the file {path.name} could not be read ({type(e).__name__})") from e
    for line in text.splitlines():
        name, separator, value = line.strip().partition("=")
        name = name.strip().removeprefix("export ").strip()
        if separator and name in KEYS_READ:
            found[name] = value.strip().strip("'\"").strip()
    return found


def values(environ: dict[str, str], env_file: str | None) -> dict[str, str]:
    """TEAMS_BOT_APP_ID and CONSOLE_HOST_NAME, from the environment first, then from the file."""
    found = {key: (environ.get(key) or "").strip() for key in KEYS_READ}
    if env_file or any(not found[key] for key in KEYS_READ):
        path = Path(env_file) if env_file else LOCAL_ENV_FILE
        if env_file or path.is_file():
            for key, value in read_env_file(path).items():
                found[key] = found[key] or value
    return found


# ---- the package --------------------------------------------------------------------------------------------------------------------------------

def package_files(bot_id: str, valid_domains: list[str]) -> dict[str, bytes]:
    return {"manifest.json": (json.dumps(manifest(bot_id, valid_domains), indent=2) + "\n").encode("utf-8"), "color.png": color_icon(), "outline.png": outline_icon()}


def zip_bytes(files: dict[str, bytes]) -> bytes:
    """The same bytes every time: sorted names, a fixed date, one compression."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_name in sorted(files):
            info = zipfile.ZipInfo(file_name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[file_name])
    return buffer.getvalue()


def outside_the_repository(folder: Path) -> Path:
    resolved = folder.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise Problem("the package goes to a folder outside the repository: it holds the client id of the app registration, which no file of the repository may hold")
    return resolved


def command_build(args, environ, out) -> int:
    found = values(environ, args.env_file)
    bot_id = found["TEAMS_BOT_APP_ID"]
    if not GUID.match(bot_id):
        raise Problem("the client id of the bot is not set or is not a GUID: set TEAMS_BOT_APP_ID in the environment, or put the line TEAMS_BOT_APP_ID=<client id> in local/hub-local.env (git ignores it) "
                      "or in the file that --env-file names. tools/entra-setup.py teams-bot prints it")
    domains = [d.strip().lower() for d in (args.valid_domain or [])] or ([found["CONSOLE_HOST_NAME"].strip().lower()] if found["CONSOLE_HOST_NAME"] else [])
    problem = next((d for d in domains if not DOMAIN.match(d)), None)
    if problem is not None:
        raise Problem("a valid domain is a host name such as pages.example.com, with no scheme, no path and no wildcard")
    folder = outside_the_repository(Path(args.out) if args.out else Path(tempfile.gettempdir()) / "meternaut-teams-app")
    files = package_files(bot_id.lower(), sorted(set(domains)))
    problems = check_manifest(json.loads(files["manifest.json"]), files)
    if problems:
        raise Problem("the package would not pass its own check: " + "; ".join(problems))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / PACKAGE_NAME
    data = zip_bytes(files)
    target.write_bytes(data)
    out(f"Wrote {target} ({len(data)} bytes).")
    if not domains:
        out("No host for the card buttons was given, so validDomains is empty and Teams will say that a button may lead to untrusted content: give --valid-domain <host>, or set CONSOLE_HOST_NAME.")
    return 0


def command_check(args, out) -> int:
    try:
        with zipfile.ZipFile(args.package) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as e:
        raise Problem(f"{Path(args.package).name} is not a package that can be read ({type(e).__name__})") from e
    try:
        document = json.loads(files.get("manifest.json", b"").decode("utf-8"))
    except ValueError as e:
        raise Problem("manifest.json is not JSON") from e
    problems = check_manifest(document, files)
    for problem in problems:
        out(f"fails: {problem}")
    return 1 if problems else 0


def main(argv=None, environ=None, out=print) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="write the Teams app package outside the repository")
    build.add_argument("--out", help="the folder for the package (outside the repository; default: meternaut-teams-app in the system's temporary folder)")
    build.add_argument("--valid-domain", action="append", help="the host that the buttons of a card open (repeat it); default CONSOLE_HOST_NAME")
    build.add_argument("--env-file", help="a file of NAME=VALUE lines that holds TEAMS_BOT_APP_ID (default: local/hub-local.env, when it is there)")
    check = commands.add_parser("check", help="check a package against the manifest rules that can be checked offline")
    check.add_argument("package")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        return command_build(args, environ, out) if args.command == "build" else command_check(args, out)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
