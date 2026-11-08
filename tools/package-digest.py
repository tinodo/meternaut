#!/usr/bin/env python3
"""Prints the digest of the app's own files: what PACKAGE_SHA256 has to be for the package that is deployed (standard library only).

    python tools/package-digest.py <folder> [--check HEX]

The folder is the one that holds `function_app.py` and the package `cases/`: the folder that the deployment zips (the build directory of tools/build-function-app.sh) or a checkout's
`src/case-functions`. The digest covers `function_app.py` and every `.py` and `.json` file in `cases/`, in the order of their paths, with line ends read as LF (cases/release.py says
exactly how), so that it is the same for the folder of a build, for the folder that the platform unpacked and for a checkout on any system. The deployment sets it as the app
setting PACKAGE_SHA256, the app computes it over its own files, and the drift check holds the two together (cases/drift.py, control A-RELEASE).

With --check HEX it prints nothing but a verdict and exits 1 when the digest of the folder is another one. It reads files and calls nothing.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "src" / "case-functions" / "cases" / "release.py"


def load_release():
    """The module that makes the digest, loaded from its file: it imports nothing of the package, and the tool then makes the digest in the way that the app does."""
    spec = importlib.util.spec_from_file_location("meternaut_release", RELEASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prints the digest of the app's own files.")
    parser.add_argument("folder", type=Path, help="the folder that holds function_app.py and the package cases/")
    parser.add_argument("--check", metavar="HEX", help="the digest that the folder is expected to have")
    args = parser.parse_args(argv)
    release = load_release()
    try:
        digest, count = release.digest(args.folder)
    except release.ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.check is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", args.check):
            print("error: --check is the SHA-256 in lower-case hexadecimal", file=sys.stderr)
            return 2
        print("the digest is the one expected" if digest == args.check else "the digest is not the one expected")
        return 0 if digest == args.check else 1
    print(digest)
    print(f"{count} files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
