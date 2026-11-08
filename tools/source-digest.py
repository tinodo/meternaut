#!/usr/bin/env python3
"""The digest of the cases app's own files (standard library only).

    python tools/source-digest.py src/case-functions            # prints 64 hexadecimal digits
    python tools/source-digest.py src/case-functions --manifest # prints one line for each file: its SHA-256 and its path

The release that the action cases publishes is named by two values that Azure keeps with the function app (docs/proposals/10-ai-security-and-governance.md, "The release that runs"): BUILD_COMMIT, the git commit
that the run was made from, and PACKAGE_SHA256, this digest of the app's own files. A digest of the zip file would change with every run (a zip holds the time of each file), so this one is of the content: for
`function_app.py` and for every `.py` and `.json` file under the package folder `cases/` (the compiled caches left out), in the order of their paths, the line "<path>\\0<SHA-256 of the file's bytes, with
CRLF read as LF>\\n", paths relative to the app's folder and with forward slashes, and then the SHA-256 of all the lines. A checkout on Windows, a checkout on Linux, the folder of a build and the folder that the
platform unpacked give the same digest, and a file that is added, removed, renamed or changed gives another one. The libraries are not in it: they are installed from requirements.txt, which carries a hash for
each of them, and the build refuses a lock without hashes, so a changed library needs a changed lock, which is a changed commit.

This is the algorithm of the app itself (src/case-functions/cases/release.py, which the in-app drift check of the agent harness runs over the files that it runs from, and which holds the result against the
setting PACKAGE_SHA256: the control A-RELEASE). The two must give the same digest for the same folder, or that control fails on every release and pulls the switch of the investigation. A test pins the digest of a
known folder, and, once cases/release.py is in the repository, holds the two to each other. Nothing is imported from the app here, so that this tool runs on a runner that has only a checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

CODE_PACKAGE = "cases"
ENTRY_FILE = "function_app.py"
SUFFIXES = (".py", ".json")
LEFT_OUT_DIRECTORIES = ("__pycache__",)


class Problem(Exception):
    """Something the caller can fix; printed without a trace."""


def files_of(root: Path, package: str = CODE_PACKAGE) -> list[tuple[str, Path]]:
    """The files that the digest covers, as (path relative to the app's folder with forward slashes, file), in the order of the paths."""
    if not root.is_dir():
        raise Problem(f"{root} is not a folder")
    code = root / package
    if not code.is_dir():
        raise Problem(f"{package}/ is not in {root}: the folder is not the folder of the app")
    found: list[tuple[str, Path]] = []
    entry = root / ENTRY_FILE
    if entry.is_file():
        found.append((ENTRY_FILE, entry))
    for path in code.rglob("*"):
        parts = path.relative_to(root).parts
        if path.is_file() and path.suffix in SUFFIXES and not any(part in LEFT_OUT_DIRECTORIES for part in parts):
            found.append(("/".join(parts), path))
    return sorted(found)


def manifest(root: Path, package: str = CODE_PACKAGE) -> list[tuple[str, str]]:
    """(SHA-256 of the file's bytes with CRLF read as LF, its path) for every file that the digest covers, in the order of the paths."""
    found = []
    for relative, path in files_of(root, package):
        try:
            data = path.read_bytes()
        except OSError:
            raise Problem(f"{relative} cannot be read") from None
        found.append((hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(), relative))
    return found


def digest(root: Path, package: str = CODE_PACKAGE) -> str:
    total = hashlib.sha256()
    for file_digest, relative in manifest(root, package):
        total.update(f"{relative}\0{file_digest}\n".encode("utf-8"))
    return total.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app", help="the app's folder, src/case-functions")
    parser.add_argument("--manifest", action="store_true", help="print the SHA-256 and the path of every file instead of the digest")
    args = parser.parse_args(argv)
    try:
        if args.manifest:
            for file_digest, relative in manifest(Path(args.app)):
                print(f"{file_digest}  {relative}")
        else:
            print(digest(Path(args.app)))
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
