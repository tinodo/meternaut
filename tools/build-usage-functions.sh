#!/usr/bin/env bash
# Builds the package of the usage function app (src/usage-functions) for the app's runtime: Linux, x86-64, Python 3.13.
#
#   bash tools/build-usage-functions.sh <build directory> [<zip file>]
#
# The libraries are downloaded as wheels for that platform (not for the machine that runs this), so the result is the
# same on every machine. The app's own platform does not build anything: that build would have to reach a public package
# index from inside the app's network. Tests are left out; so are compiled caches.
set -euo pipefail

# The libraries are wheels for Python 3.13, and the library that the Functions app is written against (azure-functions 2.x) needs
# it: pip checks that against the interpreter that runs it, so that is the one that builds. Not another one, silently.
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  echo "error: build with Python 3.13, the runtime of the function app; this is $(python3 --version 2>&1)" >&2
  exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../src/usage-functions" && pwd)"
build="${1:?the build directory is the first argument}"
zip_file="${2:-}"

rm -rf "$build"
mkdir -p "$build"
cp -r "$source_dir/function_app.py" "$source_dir/host.json" "$source_dir/requirements.txt" "$source_dir/usage" "$build/"
# Built from the lock requirements.txt: every library, direct or not, at one version, installed only when its file matches the hash
# in the lock (pip --require-hashes). requirements.in holds the four direct pins; the lock is made from it with pip-compile
# (the command is at the top of the lock), on Linux with Python 3.13, which is the app's runtime.
python3 -m pip install --quiet --disable-pip-version-check --no-compile --only-binary=:all: --require-hashes \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --implementation cp --python-version 3.13 \
  --target "$build/.python_packages/lib/site-packages" --requirement "$source_dir/requirements.txt"
find "$build" -type d -name '__pycache__' -prune -exec rm -rf {} +

if [ -n "$zip_file" ]; then
  rm -f "$zip_file"
  (cd "$build" && zip -qr "$zip_file" .)
  unzip -l "$zip_file" | tail -n 1
fi
