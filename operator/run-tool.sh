#!/bin/bash
# Runs one of the repository's check tools inside the Operator's container (docs/proposals/07-private-by-default.md).
#
# Once the services of the project are private, a tool that sends an event to Event Hubs or reads the telemetry has to run where those services can be reached: inside the network.
# tools/operator-run.py makes the container group, puts this script and the tool's files into the secret volume at /mnt/op, and reads the log. The tools are the ones the workflow ran on
# its own runner before (standard library only; the image has python3 and az). They find the signed-in identity through the Azure CLI, which this script signs in as the Operator's.
# A tool that loads another one finds it in the same folder: cases-check.py loads check-helpers.py from its own directory, so both are sent to the volume.
#
# What it reads, all from the environment (none of it is a secret):
#   OPERATOR_CLIENT_ID     client id of the user-assigned identity: az login --identity --client-id
#   OPERATOR_SUBSCRIPTION  optional: the subscription of the project, made the CLI's default after the login
#   TOOL_NAME              the tool, without its .py: lower-case letters, digits and hyphens; the file /mnt/op/<TOOL_NAME>.py has to be there
#   TOOL_ARGS              the arguments of the tool, separated by single spaces: letters, digits and . / : _ = - only. They are split on the spaces and handed to the tool as
#                          separate arguments. Nothing is evaluated, nothing is expanded, and no globbing happens (set -f), so a value cannot become a command
#   TOOL_HOLD_SECONDS      optional, 0 to 60, default 20: how long the container stays after the tool has ended. A stopped container keeps only the last 16 KB of its log, and the
#                          tool that reads the log through Azure Resource Manager polls every few seconds while the container runs: the hold lets it read the whole log
#   TOOL_VOLUME            where the secret volume is mounted (default /mnt/op): only for the tests
#
# It prints a few short lines of its own ("ok:" or "FAIL:"), then the lines of the tool, then "run-tool-done: exit code N". A string that looks like a token (a JSON Web Token, or a
# bearer token) is hidden in what the tool prints: the tools never print one, and this is the second line behind that. The exit code is the tool's. 2 means that the input was refused and
# nothing was run, 3 that the container could not run the tool (a program is missing, or the sign-in failed).
LC_ALL=C
export LC_ALL
set -u
set -f
export AZURE_CORE_COLLECT_TELEMETRY=false AZURE_CORE_NO_COLOR=true AZURE_CORE_ONLY_SHOW_ERRORS=true AZURE_CORE_LOGIN_EXPERIENCE_V2=off PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
volume=${TOOL_VOLUME:-/mnt/op}

trap 'printf "run-tool-done: exit code %s\n" "$?"' EXIT

say() {
  printf '%s: %s\n' "$1" "${2:0:120}"
}

refuse() {
  say FAIL "$1"
  exit 2
}

have() {
  command -v "$1" > /dev/null 2>&1
}

# The first line of what a command said, as plain words: ids and strings of 20 characters or more that are made of the characters of a token are hidden.
clean() {
  printf '%s' "$1" | head -n 1 | tr -c '[:print:]' ' ' \
    | sed -E 's|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|<id>|g; s|[A-Za-z0-9_.~+/=-]{20,}|<hidden>|g; s|[[:space:]]+| |g' \
    | cut -c1-70 | sed -E 's|^ +||; s| +$||'
}

# The input is checked before anything runs, and a value is never printed back: it may be anything.
guid='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
tool_name='^[a-z][a-z0-9-]{0,39}$'
command_word='^[a-z][a-z-]{0,19}$'
argument_characters='^[A-Za-z0-9 ./:_=-]+$'
seconds='^[0-9]{1,2}$'

[[ ${OPERATOR_CLIENT_ID:-} =~ $guid ]] || refuse "OPERATOR_CLIENT_ID is not the client id of an identity"
[[ -z ${OPERATOR_SUBSCRIPTION:-} || ${OPERATOR_SUBSCRIPTION:-} =~ $guid ]] || refuse "OPERATOR_SUBSCRIPTION is not a subscription id"
[[ ${TOOL_NAME:-} =~ $tool_name ]] || refuse "TOOL_NAME is not the name of a tool: lower-case letters, digits and hyphens"
tool_file="$volume/$TOOL_NAME.py"
[ -f "$tool_file" ] || refuse "the tool $TOOL_NAME.py is not in the secret volume"
args=${TOOL_ARGS:-}
[ -n "$args" ] || refuse "TOOL_ARGS is empty"
[ "${#args}" -le 600 ] || refuse "TOOL_ARGS is longer than 600 characters"
[[ $args =~ $argument_characters ]] || refuse "TOOL_ARGS holds a character that is not allowed: letters, digits and . / : _ = - and the space"
IFS=' ' read -r -a words <<< "$args"
[[ ${words[0]:-} =~ $command_word ]] || refuse "TOOL_ARGS does not start with the command of the tool"
hold=${TOOL_HOLD_SECONDS:-20}
[[ $hold =~ $seconds ]] && [ "$hold" -le 60 ] || refuse "TOOL_HOLD_SECONDS is a number from 0 to 60"

missing=""
for program in az python3 timeout sed; do
  if ! have "$program"; then
    missing="$missing $program"
  fi
done
if [ -n "$missing" ]; then
  say FAIL "not in the image:$missing"
  exit 3
fi

if version=$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2> /dev/null); then
  say ok "python3 $version"
else
  say FAIL "python3 does not run"
  exit 3
fi

# The first minute of a container group can be noisy (a name that does not resolve yet, a route that is not ready): the sign-in is tried three times. Nothing else is tried again: a tool
# that sends an event is never run twice, because an event that arrived would then start the job twice.
login=0
for attempt in 1 2 3; do
  if message=$(timeout 120 az login --identity --client-id "$OPERATOR_CLIENT_ID" --allow-no-subscriptions --output none 2>&1); then
    login=1
    break
  fi
  if [ "$attempt" -lt 3 ]; then
    sleep 10
  fi
done
if [ "$login" != 1 ]; then
  say FAIL "az login --identity: $(clean "$message")"
  exit 3
fi
say ok "az login --identity"
if [ -n "${OPERATOR_SUBSCRIPTION:-}" ]; then
  if message=$(timeout 120 az account set --subscription "$OPERATOR_SUBSCRIPTION" 2>&1); then
    say ok "az account set"
  else
    say FAIL "az account set: $(clean "$message")"
    exit 3
  fi
fi

say ok "running $TOOL_NAME.py ${words[0]}"
python3 "$tool_file" "${words[@]}" < /dev/null 2>&1 \
  | sed -u -E 's|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*|<token hidden>|g; s|([Bb]earer +)[A-Za-z0-9._~+/=-]{20,}|\1<token hidden>|g'
code=${PIPESTATUS[0]}
if [ "$hold" -gt 0 ]; then
  sleep "$hold"
fi
exit "$code"
