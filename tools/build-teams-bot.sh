#!/usr/bin/env bash
# Builds the package of the Teams bot's function app (docs/proposals/13-teams-and-outlook.md): the package `cases` of the cases app with the bot's own entry in place of the cases app's.
#
#   bash tools/build-teams-bot.sh <build directory> <zip file>
#   bash tools/build-teams-bot.sh "$RUNNER_TEMP/teams-bot" "$RUNNER_TEMP/teams-bot.zip"
#
# The bot app is public and has two functions, the messaging endpoint and the timer that offers cards (src/case-functions/teams_function_app.py). The cases app has the web page, the Watch and the
# loop's timers (src/case-functions/function_app.py), none of which may be in a public app: a Functions app registers what its function_app.py declares, and nothing else is reachable. So the
# sources are staged first, the same package and the same host.json and hash-locked requirements.txt, with the bot's entry as function_app.py, and then the one build script of the repository builds
# them (tools/build-function-app.sh, with its own FUNCTION_APP_SOURCE_DIR: the libraries are wheels for Linux and Python 3.13, installed only when they match the hashes of the lock). The bot's entry
# file is not copied next to function_app.py in the package, and the tests are left out, so the package holds one entry.
#
# FUNCTION_APP_SOURCES_ONLY=1 passes through to the build script (the sources, zipped, with no library installed): it is what the test of this script runs, on a machine that has no wheels.
set -euo pipefail

build="${1:?the build directory is the first argument}"
zip_file="${2:?the zip file is the second argument}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$here/../src/case-functions"
stage="${build}-source"

for file in teams_function_app.py host.json requirements.txt cases/teams.py; do
  if [ ! -e "$source_dir/$file" ]; then
    echo "error: $source_dir/$file is not there" >&2
    exit 1
  fi
done

rm -rf "$stage"
mkdir -p "$stage"
cp -r "$source_dir/cases" "$source_dir/host.json" "$source_dir/requirements.txt" "$stage/"
cp "$source_dir/teams_function_app.py" "$stage/function_app.py"

FUNCTION_APP_SOURCE_DIR="$stage" bash "$here/build-function-app.sh" case-functions cases "$build" "$zip_file"
