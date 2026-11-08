#!/usr/bin/env python3
"""The digest of the cases app's own files (standard library only).

    python tools/source-digest.py src/case-functions            # prints 64 hexadecimal digits
    python tools/source-digest.py src/case-functions --manifest # prints one line for each file: its SHA-256 and its path

The release that the action cases publishes is named by two values that Azure keeps with the function app (docs/proposals/10-ai-security-and-governance.md, "The release that runs"): BUILD_COMMIT, the git commit
that the run was made from, and PACKAGE_SHA256, this digest. A digest of the zip file would change with every run (a zip holds the time of each file), so this one is of the content: for each file that the
build puts in the package (tools/build-function-app.sh copies exactly these, and leaves out the tests and the compiled caches), the line "<path>\\0<SHA-256 of its bytes>\\n", paths with forward slashes and
in sorted order, and the SHA-256 of all the lines. The libraries are not in it: they are installed from requirements.txt, which carries a hash for each of them and is one of the files below, so the digest
fixes the package as far as the build is deterministic. The same function can be run on any machine for any commit, and the app can run it over its own files when it starts (the in-app check of the agent
harness, `cases/drift.py`, has to use this very algorithm: a test of tools/tests/test_source_digest.py pins the lines of a known folder, so a change here is a change there).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

TOP_LEVEL_FILES = ("function_app.py", "host.json", "requirements.txt")
CODE_PACKAGE = "cases"
LEFT_OUT_DIRECTORIES = ("__pycache__",)
LEFT_OUT_SUFFIXES = (".pyc", ".pyo")


class Problem(Exception):
    """Something the caller can fix; printed without a trace."""


def files_of(root: Path, package: str = CODE_PACKAGE) -> list[tuple[str, Path]]:
    """The files of the package, as (path relative to the app's folder with forward slashes, file), in sorted order of the path."""
    if not root.is_dir():
        raise Problem(f"{root} is not a folder")
    found: list[tuple[str, Path]] = []
    for name in TOP_LEVEL_FILES:
        path = root / name
        if not path.is_file():
            raise Problem(f"{name} is not in {root}: the folder is not a function app of this repository")
        found.append((name, path))
    code = root / package
    if not code.is_dir():
        raise Problem(f"{package}/ is not in {root}: the folder is not a function app of this repository")
    for path in code.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in LEFT_OUT_DIRECTORIES for part in relative.parts) or path.suffix in LEFT_OUT_SUFFIXES:
            continue
        found.append((relative.as_posix(), path))
    return sorted(found)


def manifest(root: Path, package: str = CODE_PACKAGE) -> list[tuple[str, str]]:
    """(SHA-256 of the file's bytes, its path) for every file of the package."""
    return [(hashlib.sha256(path.read_bytes()).hexdigest(), relative) for relative, path in files_of(root, package)]


def digest(root: Path, package: str = CODE_PACKAGE) -> str:
    total = hashlib.sha256()
    for file_digest, relative in sorted(manifest(root, package), key=lambda entry: entry[1]):
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
