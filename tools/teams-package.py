#!/usr/bin/env python3
"""Builds the Teams app package of Meternaut and checks it (standard library only).

    python tools/teams-package.py build --bot-id <client id of the bot's identity> --site https://<console host> --out teams-app.zip [--version 1.0.0] [--app-id <guid>] [--force]
    python tools/teams-package.py check teams-app.zip
    python tools/teams-package.py manifest --bot-id <client id> --site https://<console host>

The package is the zip that Teams admin center takes under "Upload custom apps" (docs/proposals/13-teams-and-outlook.md has the steps): a manifest and two icons, at the root of the
zip. Nothing is downloaded and nothing is signed; the icons are drawn here with zlib and struct, so that no binary file is kept in the repository, and the zip is the same bytes for
the same arguments (fixed timestamps, fixed order). The bot id is the client id of the user-assigned identity that IS the bot (the output `botClientId` of the action `teams`).

What the manifest says (schema v1.30, the current one on 2026-11-08, from https://learn.microsoft.com/microsoftteams/platform/resources/schema/manifest-schema):
- one bot, in the personal scope only: a card channel between one person and Meternaut, never a channel, a team or a group chat;
- `isNotificationOnly` is false, because a card can be answered (the Universal Actions that the cards use call the bot);
- no valid domains: the cards open the web page in the browser, and nothing is loaded inside Teams; no single sign-in (`webApplicationInfo`): the person that taps is named by Teams
  and checked against the list of people (cases/teams.py), and an approval of a change is made on the web page, where the person signs in to Azure;
- the name ends with "(AI)": the sender of every message of Meternaut says that an AI wrote it (AGENTS.md rule 13 (d)).

`check` applies what Teams applies when a package is uploaded (lengths, shapes, the files and the icons' size) plus the choices above, and prints every problem. It exits 1 when there is one.
"""
from __future__ import annotations

import argparse
import functools
import io
import json
import re
import struct
import sys
import uuid
import zipfile
import zlib
from pathlib import Path

SCHEMA_VERSION = "1.30"
SCHEMA_URL = f"https://developer.microsoft.com/json-schemas/teams/v{SCHEMA_VERSION}/MicrosoftTeams.schema.json"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SITE = re.compile(r"^https://[a-z0-9]([a-z0-9.-]{0,200}[a-z0-9])?(:[0-9]{1,5})?$")
URL = re.compile(r"^https://[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]{0,200})?$")
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
FILES = ("manifest.json", "color.png", "outline.png")
ICONS = {"color": ("color.png", 192), "outline": ("outline.png", 32)}
MAX_PACKAGE = 1024 * 1024
NAME = "Meternaut (AI)"
ACCENT = "#0B5CAD"
KEYS = {"$schema", "manifestVersion", "version", "id", "developer", "name", "description", "icons", "accentColor", "bots", "validDomains"}
SHORT_DESCRIPTION = "An AI that tells you about Azure costs and asks you to decide."
FULL_DESCRIPTION = ("Meternaut is an AI that looks for Azure resources that cost money and are not used. When a decision waits for you, it sends a card here. "
                    "A change to Azure is never made from a card: you open the page, sign in to Azure and decide there, and Azure checks your own rights. "
                    "Answers that change nothing in Azure, such as a question or \"this is not mine\", are recorded from the card. Written by an AI; a person approves every change.")
NAMESPACE = uuid.UUID("6f1d3c52-8a47-4b7e-9c35-2d9b0e41a7c8")  # a fixed namespace, so that the id of the Teams app is the same on every build for one bot
# "M", seven columns and seven rows: the mark of both icons
GLYPH = ("X.....X", "XX...XX", "X.X.X.X", "X..X..X", "X.....X", "X.....X", "X.....X")


class PackageError(Exception):
    """A package that cannot be made. The text says why."""


# -- the icons ----------------------------------------------------------------------------------------------------------------------------------

def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png(width: int, height: int, pixel) -> bytes:
    """A PNG of RGBA pixels: `pixel(x, y)` gives (r, g, b, a). Eight bits, no interlacing, filter 0."""
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b"")


def _mark(size: int, scale: int, x: int, y: int) -> bool:
    """True when the pixel is on the glyph, drawn at `scale` pixels to the cell and centred in a square of `size` pixels."""
    offset = (size - 7 * scale) // 2
    column, row = (x - offset) // scale, (y - offset) // scale
    return 0 <= column < 7 and 0 <= row < 7 and x >= offset and y >= offset and GLYPH[row][column] == "X"


@functools.lru_cache(maxsize=None)
def color_icon() -> bytes:
    """192 by 192: a white M on the accent colour."""
    r, g, b = (int(ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    return png(192, 192, lambda x, y: (255, 255, 255, 255) if _mark(192, 16, x, y) else (r, g, b, 255))


@functools.lru_cache(maxsize=None)
def outline_icon() -> bytes:
    """32 by 32: a white M on a transparent ground, which is what Teams asks of the outline icon."""
    return png(32, 32, lambda x, y: (255, 255, 255, 255) if _mark(32, 3, x, y) else (0, 0, 0, 0))


def read_png(data: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """(width, height, pixels) of a PNG that this module draws (RGBA, eight bits, filter 0). PackageError for any other."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PackageError("not a PNG")
    position, header, joined, ended = 8, None, b"", False
    while position + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        if len(body) != length or data[position + 8 + length:position + 12 + length] != struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF):
            raise PackageError("a chunk of the PNG is cut or its checksum is wrong")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            joined += body
        elif kind == b"IEND":
            ended = True
        position += 12 + length
    if header is None or header[2:] != (8, 6, 0, 0, 0):
        raise PackageError("the PNG is not RGBA with eight bits and no interlacing")
    if ended is False:
        raise PackageError("the PNG has no end chunk")
    width, height = header[0], header[1]
    try:
        raw = zlib.decompress(joined)
    except zlib.error as error:
        raise PackageError("the pixels of the PNG cannot be read") from error
    stride = 1 + width * 4
    if len(raw) != stride * height or any(raw[row * stride] != 0 for row in range(height)):
        raise PackageError("the PNG uses a filter that this check does not read")
    pixels = [tuple(raw[row * stride + 1 + column * 4:row * stride + 5 + column * 4]) for row in range(height) for column in range(width)]
    return width, height, pixels  # type: ignore[return-value]


# -- the manifest -------------------------------------------------------------------------------------------------------------------------------

def app_id_of(bot_id: str) -> str:
    """The id of the Teams app for a bot: a fixed function of the bot's id, so that a later build of the same bot is an update of the same app in the catalog."""
    return str(uuid.uuid5(NAMESPACE, bot_id.lower()))


def manifest(bot_id: str, site: str, version: str = "1.0.0", app_id: str | None = None) -> dict:
    """The manifest. `site` is the address of the web page (https://host): the developer's addresses are pages of it, and nothing is fetched from them."""
    if not GUID.match(bot_id or ""):
        raise PackageError("the bot id is the client id of the bot's identity, a GUID")
    if not SITE.match(site or ""):
        raise PackageError("the site is the address of the web page, like https://host")
    if not SEMVER.match(version or ""):
        raise PackageError("the version is three numbers, like 1.0.0")
    if app_id is not None and not GUID.match(app_id):
        raise PackageError("the app id is a GUID")
    return {
        "$schema": SCHEMA_URL,
        "manifestVersion": SCHEMA_VERSION,
        "version": version,
        "id": (app_id or app_id_of(bot_id)).lower(),
        "developer": {"name": "Meternaut", "websiteUrl": f"{site}/", "privacyUrl": f"{site}/me/settings", "termsOfUseUrl": f"{site}/"},
        "name": {"short": NAME, "full": NAME},
        "description": {"short": SHORT_DESCRIPTION, "full": FULL_DESCRIPTION},
        "icons": {"color": ICONS["color"][0], "outline": ICONS["outline"][0]},
        "accentColor": ACCENT,
        "bots": [{"botId": bot_id.lower(), "scopes": ["personal"], "isNotificationOnly": False, "supportsFiles": False}],
        "validDomains": [],
    }


def files_of(bot_id: str, site: str, version: str = "1.0.0", app_id: str | None = None) -> dict[str, bytes]:
    text = json.dumps(manifest(bot_id, site, version, app_id), indent=2, ensure_ascii=True) + "\n"
    return {"manifest.json": text.encode("ascii"), "color.png": color_icon(), "outline.png": outline_icon()}


def zip_bytes(files: dict[str, bytes]) -> bytes:
    """The zip of the files: in the order of FILES, at the root, with the time of the zip format's own epoch, so that the same files are the same bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type, item.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(item, files[name])
    return buffer.getvalue()


# -- the check ----------------------------------------------------------------------------------------------------------------------------------

def _text(problems: list[str], where: str, value: object, low: int, high: int, ends: str | None = None) -> None:
    if not isinstance(value, str) or not low <= len(value) <= high:
        problems.append(f"{where} is a text of {low} to {high} characters")
    elif ends and not value.endswith(ends):
        problems.append(f'{where} ends with "{ends}": the sender of every message of Meternaut says that an AI wrote it')


def problems_of(files: dict[str, bytes]) -> list[str]:
    """Every way that a package is not what Teams takes, or not what Meternaut chose. An empty list is a package that passes."""
    found: list[str] = []
    if set(files) != set(FILES):
        return [f"the zip holds {', '.join(sorted(files)) or 'nothing'} and has to hold exactly {', '.join(FILES)} at its root"]
    try:
        document = json.loads(files["manifest.json"].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ["manifest.json is not JSON"]
    if not isinstance(document, dict):
        return ["manifest.json is not a JSON object"]
    if set(document) != KEYS:
        found.append(f"the manifest has the keys {', '.join(sorted(set(document) ^ KEYS))} that it should not have or lacks (it has exactly {', '.join(sorted(KEYS))})")
    if document.get("$schema") != SCHEMA_URL or document.get("manifestVersion") != SCHEMA_VERSION:
        found.append(f"$schema and manifestVersion are the schema v{SCHEMA_VERSION}")
    if not isinstance(document.get("version"), str) or not SEMVER.match(document["version"]):
        found.append("version is three numbers, like 1.0.0")
    if not isinstance(document.get("id"), str) or not GUID.match(document["id"]):
        found.append("id is a GUID")
    developer = document.get("developer") if isinstance(document.get("developer"), dict) else {}
    _text(found, "developer.name", developer.get("name"), 1, 32)
    for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
        if not isinstance(developer.get(key), str) or not URL.match(developer[key]) or len(developer[key]) > 2048:
            found.append(f"developer.{key} is an https address")
    if set(developer) != {"name", "websiteUrl", "privacyUrl", "termsOfUseUrl"}:
        found.append("developer has a name and the three addresses, and nothing else")
    name = document.get("name") if isinstance(document.get("name"), dict) else {}
    _text(found, "name.short", name.get("short"), 1, 30, "(AI)")
    _text(found, "name.full", name.get("full"), 1, 100, "(AI)")
    description = document.get("description") if isinstance(document.get("description"), dict) else {}
    _text(found, "description.short", description.get("short"), 1, 80)
    _text(found, "description.full", description.get("full"), 1, 4000)
    if not isinstance(document.get("accentColor"), str) or not COLOR.match(document["accentColor"]):
        found.append("accentColor is a colour like #0B5CAD")
    if document.get("icons") != {"color": "color.png", "outline": "outline.png"}:
        found.append("icons name color.png and outline.png")
    if document.get("validDomains") != []:
        found.append("validDomains is empty: nothing is loaded inside Teams")
    bots = document.get("bots")
    if not isinstance(bots, list) or len(bots) != 1 or not isinstance(bots[0], dict):
        found.append("bots holds exactly one bot")
    else:
        bot = bots[0]
        if not isinstance(bot.get("botId"), str) or not GUID.match(bot["botId"]):
            found.append("bots[0].botId is a GUID: the client id of the bot's identity")
        if bot.get("scopes") != ["personal"]:
            found.append('bots[0].scopes is ["personal"]: a card channel between one person and Meternaut')
        if bot.get("isNotificationOnly") is not False or bot.get("supportsFiles") is not False or set(bot) != {"botId", "scopes", "isNotificationOnly", "supportsFiles"}:
            found.append("bots[0] has isNotificationOnly and supportsFiles false, and nothing else but its id and scopes")
    for kind, (name_of, size) in ICONS.items():
        try:
            width, height, pixels = read_png(files[name_of])
        except PackageError as error:
            found.append(f"{name_of}: {error}")
            continue
        if (width, height) != (size, size):
            found.append(f"{name_of} is {size} by {size} pixels, not {width} by {height}")
        elif kind == "outline" and not all(p in ((255, 255, 255, 255), (0, 0, 0, 0)) for p in pixels):
            found.append("outline.png is white on a transparent ground, and nothing else")
    if sum(len(data) for data in files.values()) > MAX_PACKAGE:
        found.append("the package is larger than 1 MiB")
    return found


def read_zip(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PackageError("the zip holds a name twice")
            if any(item.file_size > MAX_PACKAGE for item in archive.infolist()):
                raise PackageError("a file of the zip is larger than 1 MiB")
            return {name: archive.read(name) for name in names}
    except (zipfile.BadZipFile, OSError) as error:
        raise PackageError(f"{path} is not a zip that can be read") from error


# -- the command line ---------------------------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None, out=None) -> int:
    out = sys.stdout if out is None else out
    parser = argparse.ArgumentParser(description="Builds and checks the Teams app package of Meternaut.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "manifest"):
        command = commands.add_parser(name)
        command.add_argument("--bot-id", required=True, help="the client id of the user-assigned identity that is the bot (the output botClientId of the action teams)")
        command.add_argument("--site", required=True, help="the address of the web page, like https://host")
        command.add_argument("--version", default="1.0.0", help="three numbers; raise it for a new upload of the same app")
        command.add_argument("--app-id", default=None, help="the id of the Teams app; the default is a fixed function of the bot id")
        if name == "build":
            command.add_argument("--out", required=True, help="the zip to write")
            command.add_argument("--force", action="store_true", help="replace the zip if it exists")
    check = commands.add_parser("check")
    check.add_argument("package", help="the zip to check")
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            out.write(json.dumps(manifest(args.bot_id, args.site, args.version, args.app_id), indent=2) + "\n")
            return 0
        if args.command == "check":
            found = problems_of(read_zip(Path(args.package)))
            for problem in found:
                out.write(f"problem: {problem}\n")
            out.write("The package passes.\n" if not found else f"{len(found)} problem(s).\n")
            return 1 if found else 0
        target = Path(args.out)
        if target.exists() and not args.force:
            raise PackageError(f"{target} exists: --force replaces it")
        files = files_of(args.bot_id, args.site, args.version, args.app_id)
        found = problems_of(files)
        if found:
            raise PackageError("the package would not pass its own check: " + "; ".join(found))
        target.write_bytes(zip_bytes(files))
        out.write(f"Wrote {target} ({target.stat().st_size} bytes): the Teams app {json.loads(files['manifest.json'])['id']}, version {args.version}, for the bot {args.bot_id.lower()}.\n")
        return 0
    except PackageError as error:
        out.write(f"error: {error}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
