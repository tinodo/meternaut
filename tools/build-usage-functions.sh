#!/usr/bin/env bash
# Builds the package of the usage function app (src/usage-functions) for the app's runtime: Linux, x86-64, Python 3.13.
#
#   bash tools/build-usage-functions.sh <build directory> [<zip file>]
#
# The libraries are downloaded as wheels for that platform (not for the machine that runs this), so the result is the
# same on every machine. The app's own platform does not build anything: that build would have to reach a public package
# index from inside the app's network. Tests are left out; so are compiled caches.
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../src/usage-functions" && pwd)"
build="${1:?the build directory is the first argument}"
zip_file="${2:-}"

rm -rf "$build"
mkdir -p "$build"
cp -r "$source_dir/function_app.py" "$source_dir/host.json" "$source_dir/requirements.txt" "$source_dir/usage" "$build/"
python3 -m pip install --quiet --disable-pip-version-check --no-compile --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --implementation cp --python-version 3.13 \
  --target "$build/.python_packages/lib/site-packages" --requirement "$source_dir/requirements.txt"
find "$build" -type d -name '__pycache__' -prune -exec rm -rf {} +

if [ -n "$zip_file" ]; then
  rm -f "$zip_file"
  (cd "$build" && zip -qr "$zip_file" .)
  unzip -l "$zip_file" | tail -n 1
fi
