"""The digest of the app's own files: what is running, as one hash that a person can hold against what was built.

The hash is made over the files that are the app's own, in a fixed order: `function_app.py` next to the package, and every `.py` and `.json` file in the package folder `cases/` (the
lock of the agents is one of them), without the compiled caches. For each file the line `<path with / and relative to the app folder>\\0<SHA-256 of the bytes, with CRLF read as LF>` is
hashed, in the order of the paths, so that a checkout on Windows and one on Linux, and the folder of a build and the folder that the platform unpacked, give the same hash. A file
that is added, removed, renamed or changed gives another one.

The deployment workflow computes it from the folder that it zips (`python tools/package-digest.py <folder>`) and sets it as the app setting PACKAGE_SHA256; the app computes it over
its own files at its start and the drift check holds the two together (cases/drift.py, control A-RELEASE). This module is standard library only and imports nothing of the package, so
that the tool can load it from its own folder.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE = "cases"
ENTRY = "function_app.py"
SUFFIXES = (".py", ".json")
SKIPPED = ("__pycache__",)


class ReleaseError(Exception):
    """The folder is not the folder of the app, or a file of it cannot be read."""


def app_folder() -> Path:
    """The folder of the app that is running: the one that holds the package `cases/` and `function_app.py`."""
    return Path(__file__).resolve().parent.parent


def files_of(folder: Path) -> list[tuple[str, Path]]:
    """The files that the digest covers, as (path relative to the folder, file), in the order of the paths."""
    package = folder / PACKAGE
    if not package.is_dir():
        raise ReleaseError(f"{folder} holds no folder {PACKAGE}: it is not the folder of the app")
    found: list[tuple[str, Path]] = []
    entry = folder / ENTRY
    if entry.is_file():
        found.append((ENTRY, entry))
    for path in package.rglob("*"):
        parts = path.relative_to(folder).parts
        if path.is_file() and path.suffix in SUFFIXES and not any(part in SKIPPED for part in parts):
            found.append(("/".join(parts), path))
    return sorted(found)


def digest(folder: Path) -> tuple[str, int]:
    """The digest of the app's own files in a folder, and how many files it covers."""
    files = files_of(Path(folder))
    total = hashlib.sha256()
    for name, path in files:
        try:
            data = path.read_bytes()
        except OSError:
            raise ReleaseError(f"{name} cannot be read") from None
        data = data.replace(b"\r\n", b"\n")
        total.update(f"{name}\0{hashlib.sha256(data).hexdigest()}\n".encode("utf-8"))
    return total.hexdigest(), len(files)
