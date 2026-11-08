#!/usr/bin/env bash
# Builds the package of a function app of this repository (src/<app>) for the apps' runtime: Linux, x86-64, Python 3.13.
#
#   bash tools/build-function-app.sh <app directory under src> <name of its code package> <build directory> [<zip file>]
#   bash tools/build-function-app.sh case-functions cases "$RUNNER_TEMP/case-functions" "$RUNNER_TEMP/case-functions.zip"
#
# The libraries are downloaded as wheels for that platform (not for the machine that runs this), so the result is the
# same on every machine. The app's own platform does not build anything: that build would have to reach a public package
# index from inside the app's network. Tests are left out; so are compiled caches.
#
# The app is built a second way too, because its package is too big for the request that makes the Operator's container group (the cases app's is 614,068 bytes zipped,
# and a request takes at most 480,000 bytes of files: tools/operator-run.py has the evidence), and its code is published from inside the network (docs/proposals/07-private-by-default.md,
# phase 2): the workflow sends the sources, and operator/publish.sh builds the libraries in the container. It is still this one script, with three switches, each set only by the caller that needs it,
# so that there is one build command and one layout:
#   FUNCTION_APP_SOURCES_ONLY=1       the app's own files and no libraries, zipped: the sources that the workflow sends to the Operator (nothing is installed, so no interpreter is checked)
#   FUNCTION_APP_SOURCE_DIR=<folder>  where the app's files are, in place of src/<app> next to this script: the folder in which the Operator unpacked those sources
#   FUNCTION_APP_BUILD_IN_OPERATOR=1  the build runs in the Operator's container (operator/publish.sh). Its Python is 3.12, and pip is the one that ensurepip made. The libraries are still the wheels
#                                     for Python 3.13: pip is told so (--python-version below) and checks the Requires-Python of a library against that target and not against the interpreter that
#                                     runs it, which the probe of the Operator showed on the real estate (azure-functions 2.x built under 3.12 with no --ignore-requires-python). So the guard is
#                                     another one here: pip has to run, the lock has to carry hashes, and no compiled module of the result may be for another Python than 3.13. The image has
#                                     no zip, unzip or find that anything may rely on: Python makes the zip and counts it, and the caches are pruned only where find is there
set -euo pipefail

sources_only="${FUNCTION_APP_SOURCES_ONLY:-}"
in_operator="${FUNCTION_APP_BUILD_IN_OPERATOR:-}"
for switch in "$sources_only" "$in_operator"; do
  if [ -n "$switch" ] && [ "$switch" != 1 ]; then
    echo "error: FUNCTION_APP_SOURCES_ONLY and FUNCTION_APP_BUILD_IN_OPERATOR are 1 or not set" >&2
    exit 1
  fi
done
if [ -n "$sources_only" ] && [ -n "$in_operator" ]; then
  echo "error: FUNCTION_APP_SOURCES_ONLY and FUNCTION_APP_BUILD_IN_OPERATOR are not set together" >&2
  exit 1
fi

# The libraries are wheels for Python 3.13, and the library that the Functions app is written against (azure-functions 2.x) needs it. On the runner the interpreter that builds is 3.13 and not
# another one, silently: pip was first read to check the Requires-Python of a library against the interpreter that runs it. In the Operator the guard is the other one that the header describes.
if [ -n "$sources_only" ]; then
  : # nothing is installed
elif [ -n "$in_operator" ]; then
  if ! python3 -m pip --version > /dev/null 2>&1; then
    echo "error: pip does not run in this Python; the build in the Operator needs the pip that ensurepip makes" >&2
    exit 1
  fi
elif ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  echo "error: build with Python 3.13, the runtime of the function app; this is $(python3 --version 2>&1)" >&2
  exit 1
fi

app="${1:?the app directory under src is the first argument}"
package="${2:?the name of the code package of the app is the second argument}"
build="${3:?the build directory is the third argument}"
zip_file="${4:-}"
if [[ ! "$app" =~ ^[a-z0-9-]+$ ]] || [[ ! "$package" =~ ^[a-z0-9_]+$ ]]; then
  echo "error: the app directory and the package name are plain lowercase names" >&2
  exit 1
fi
if [ -n "$zip_file" ]; then
  case "$zip_file" in
    /*) ;;
    *) zip_file="$PWD/$zip_file" ;;
  esac
fi
if [ -n "$sources_only" ] && [ -z "$zip_file" ]; then
  echo "error: the sources are zipped: the fourth argument is the zip file" >&2
  exit 1
fi
if [ -n "${FUNCTION_APP_SOURCE_DIR:-}" ]; then
  source_dir="$(cd "$FUNCTION_APP_SOURCE_DIR" && pwd)"
else
  source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../src/$app" && pwd)"
fi
if [ -n "$in_operator" ] && ! grep -q -- '--hash=sha256:' "$source_dir/requirements.txt"; then
  echo "error: the lock $source_dir/requirements.txt carries no hashes: pip would refuse it (--require-hashes)" >&2
  exit 1
fi

rm -rf "$build"
mkdir -p "$build"
cp -r "$source_dir/function_app.py" "$source_dir/host.json" "$source_dir/requirements.txt" "$source_dir/$package" "$build/"
if [ -z "$sources_only" ]; then
  # Built from the lock requirements.txt: every library, direct or not, at one version, installed only when its file matches the hash
  # in the lock (pip --require-hashes). requirements.in holds the direct pins; the lock is made from it with pip-compile
  # (the command is at the top of the lock), on Linux with Python 3.13, which is the app's runtime.
  python3 -m pip install --quiet --disable-pip-version-check --no-compile --only-binary=:all: --require-hashes \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --implementation cp --python-version 3.13 \
    --target "$build/.python_packages/lib/site-packages" --requirement "$source_dir/requirements.txt"
fi
if [ -n "$in_operator" ]; then
  # Another interpreter than 3.13 ran pip: what it chose has to be for 3.13 all the same, and a compiled module of another version in the result would not load in the app.
  python3 -c '
import os, re, sys
foreign = sorted({name for _, _, files in os.walk(sys.argv[1]) for name in files if re.search(r"\.cpython-3[0-9]+-", name) and not re.search(r"\.cpython-313-", name)})
if foreign:
    print("error: compiled modules for another Python than 3.13, the runtime of the function app: " + ", ".join(foreign[:3]), file=sys.stderr)
    sys.exit(1)
' "$build/.python_packages/lib/site-packages"
fi
if [ -z "$in_operator" ] || command -v find > /dev/null 2>&1; then
  find "$build" -type d -name '__pycache__' -prune -exec rm -rf {} +
fi

if [ -n "$zip_file" ]; then
  rm -f "$zip_file"
  if [ -z "$in_operator" ] && command -v zip > /dev/null 2>&1; then
    (cd "$build" && zip -qr "$zip_file" .)
  else
    python3 -c '
import os, sys, zipfile
root, target = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if name != "__pycache__")
        for name in sorted(files):
            path = os.path.join(folder, name)
            archive.write(path, os.path.relpath(path, root).replace(os.sep, "/"))
' "$build" "$zip_file"
  fi
  if [ -z "$in_operator" ] && command -v unzip > /dev/null 2>&1; then
    unzip -l "$zip_file" | tail -n 1
  else
    python3 -c 'import sys, zipfile; print("%d files" % len(zipfile.ZipFile(sys.argv[1]).namelist()))' "$zip_file"
  fi
fi
