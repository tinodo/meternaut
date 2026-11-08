#!/bin/bash
# The probe of the Operator: what a container in the Operator's subnet can do, said in short lines (docs/proposals/07-private-by-default.md).
#
# It runs inside the container that tools/operator-run.py makes in the Operator's subnet, with the image mcr.microsoft.com/azure-cli (bash, az, python3, curl, getent and
# the coreutils; no jq, no awk and no find are assumed). It prints at most 120 short lines, one "ok:" or "FAIL:" line for each check, and never a token, a key or a
# secret: what a command says is cut to a few words, and ids and long strings in it are hidden. The log of a stopped container is cut at 16 KB or 1,000 lines, so the probe
# stays far below both. The last line is always "probe-done", and the exit code is always 0: the facts are the product, and a failed check is a line, not a failure of the run.
#
# What it reads, all from the environment (none of it is a secret, except the one that says so):
#   OPERATOR_CLIENT_ID     client id of the user-assigned identity: az login --identity --client-id
#   OPERATOR_GROUP         the project's resource group, read with the identity's token and with the deploy identity's
#   OPERATOR_SUBSCRIPTION  optional: the subscription of that group, when the login does not find it by itself
#   PROBE_NAMES            host names to look up, separated by spaces; each is said private or public
#   PROBE_PRIVATE_NAMES    optional: the names among them, and among PROBE_SCM_HOSTS, that must resolve to a private address (a public answer is then a FAIL)
#   PROBE_URLS             https addresses to reach, separated by spaces: the status code, or what went wrong (at most two redirects are followed)
#   PROBE_SIZE_BYTES       the size that /mnt/op/size-test was sent with, when the secret volume carries that file
#   PROBE_SCM_HOSTS        the deployment sites of the function apps (<app>.scm.azurewebsites.net), separated by spaces: each is said private or public, with the status of
#                          an unauthenticated GET of / (no redirect is followed, and no content is read)
#   PROBE_DEPLOY_CLIENT_ID, PROBE_DEPLOY_TENANT_ID
#                          the deploy identity, the one that the workflow signs in as, and its tenant: az login --service-principal --federated-token
#   AZURE_FEDERATED_TOKEN  THE ONE SECRET: the OpenID Connect token that GitHub issued to the run (audience api://AzureADTokenExchange, valid for five minutes), sent as a
#                          secure environment variable. It is read once at the start and taken out of the environment, so that nothing that runs below inherits it, and it is
#                          never printed: it is handed to the az login of the deploy identity and to nothing else
#   PROBE_TOKEN_NOTE       optional: why the workflow could not get that token, in a few words; the FAIL line of the deploy identity's sign-in says it
#   PROBE_LOCK_BYTES       the size that /mnt/op/cases-requirements.txt, the lock file of the cases app's libraries, was sent with
#   PROBE_VOLUME           where the secret volume is mounted (default /mnt/op); PROBE_RESOLV_CONF the resolver file (default /etc/resolv.conf); PROBE_TMP where the work folder
#                          of the probe is made (default /tmp): all three only for the tests
LC_ALL=C
export LC_ALL
set -u
set -f
export AZURE_CORE_COLLECT_TELEMETRY=false AZURE_CORE_NO_COLOR=true AZURE_CORE_ONLY_SHOW_ERRORS=true AZURE_CORE_LOGIN_EXPERIENCE_V2=off
volume=${PROBE_VOLUME:-/mnt/op}
resolv_conf=${PROBE_RESOLV_CONF:-/etc/resolv.conf}

# The token is read once and taken out of the environment: no command below inherits it, and it is used for one thing, the sign-in as the deploy identity.
federated_token=${AZURE_FEDERATED_TOKEN:-}
unset AZURE_FEDERATED_TOKEN

# A folder of its own for what this probe makes (the Azure CLI's state of the deploy identity, and the build test), removed at the end whatever happens.
tmp_root=${PROBE_TMP:-/tmp}
work=$(mktemp -d "$tmp_root/probe-XXXXXX" 2> /dev/null) || work=""

MAX_LINES=120
printed=0
full=0

finish() {
  case "$work" in
    "$tmp_root"/probe-?*) rm -rf "$work" ;;
  esac
  printf 'probe-done\n'
  exit 0
}
trap finish EXIT

# say ok|FAIL "a few words": one line, cut to 90 characters. At most MAX_LINES - 2 of them, so that the notice and the last line always fit.
say() {
  if [ "$full" = 1 ]; then
    return 0
  fi
  if [ "$printed" -ge $((MAX_LINES - 2)) ]; then
    full=1
    printf 'FAIL: more checks than %s lines hold; the rest was left out\n' "$MAX_LINES"
    return 0
  fi
  printf '%s: %s\n' "$1" "${2:0:90}"
  printed=$((printed + 1))
}

have() {
  command -v "$1" > /dev/null 2>&1
}

# The first line of what a command said, as plain words: ids and strings of 20 characters or more that are made of the characters of a token are hidden, so that nothing
# like a token can pass.
clean() {
  printf '%s' "$1" | head -n 1 | tr -c '[:print:]' ' ' \
    | sed -E 's|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|<id>|g; s|[A-Za-z0-9_.~+/=-]{20,}|<hidden>|g; s|[[:space:]]+| |g' \
    | cut -c1-70 | sed -E 's|^ +||; s| +$||'
}

# private (10., 172.16 to 172.31, 192.168.) or public, for a dotted IPv4 address
class_of() {
  case "$1" in
    10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) echo private ;;
    *:*) echo "an IPv6 address" ;;
    *) echo public ;;
  esac
}

why() {
  case "$1" in
    6) echo "name not resolved" ;;
    7) echo "connection refused" ;;
    28) echo "timed out" ;;
    35) echo "TLS handshake failed" ;;
    51 | 60) echo "certificate not trusted" ;;
    52) echo "empty reply" ;;
    56) echo "connection reset" ;;
    *) echo "failed" ;;
  esac
}

# The first line of what pip said that starts with ERROR, or else its first line.
first_error_of() {
  local line
  while IFS= read -r line; do
    case "$line" in
      ERROR*) printf '%s' "$line"; return 0 ;;
    esac
  done <<< "$1"
  printf '%s' "${1%%$'\n'*}"
}

# What pip said, in a few words; capital letters do not matter. The order is the order of the likely causes: a hash that does not match, a network that does not answer, and then
# the interpreter that does not fit the Requires-Python of a library.
pip_reason() {
  local said
  said=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$said" in
    *"do not match the hashes"* | *"hash mismatch"*) echo "a hash does not match the lock" ;;
    *certificate_verify_failed* | *sslerror*) echo "pip does not trust the certificate" ;;
    *"name resolution"* | *"name or service not known"* | *nameresolutionerror*) echo "a name was not resolved" ;;
    *"connection refused"* | *"failed to establish a new connection"* | *"max retries exceeded"* | *connectionerror*) echo "the connection failed" ;;
    *"timed out"* | *readtimeout* | *connecttimeout*) echo "timed out" ;;
    *"different python version"* | *"requires a different python"* | *requires-python*) echo "Requires-Python does not fit the interpreter" ;;
    *"no matching distribution"* | *"could not find a version"*) echo "no matching distribution" ;;
    *) clean "$(first_error_of "$1")" ;;
  esac
}

# "311 files, 52.3 MB" for everything below a folder. Python counts them: find is not assumed to be in the image.
stats() {
  python3 -c 'import os, sys; sizes = [os.lstat(os.path.join(r, f)).st_size for r, _, files in os.walk(sys.argv[1]) for f in files]; print("%d files, %.1f MB" % (len(sizes), sum(sizes) / 1048576))' "$1" 2> /dev/null \
    || echo "files not counted"
}

# The tools of the image. Nothing else is assumed.
missing=""
for tool in az curl getent python3; do
  if ! have "$tool"; then
    missing="$missing $tool"
  fi
done
if [ -z "$missing" ]; then
  say ok "az, curl, getent and python3 are in the image"
else
  say FAIL "not in the image:$missing"
fi

if have python3; then
  if version=$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2> /dev/null); then
    say ok "python3 $version"
  else
    say FAIL "python3 does not run"
  fi
fi

# pip, which the build test at the end needs. When python3 has none, the answer to whether ensurepip can make one is part of the report, and the test then goes on with the pip
# that ensurepip made in the work folder (the system's python is not changed).
pip_ok=0
pip_python_path=""
if have python3; then
  pip_line=$(python3 -m pip --version 2>&1 | head -n 1)
  case "$pip_line" in
    "pip "[0-9]*)
      pip_version=${pip_line#pip }
      pip_version=${pip_version%% *}
      pip_ok=1
      say ok "python3 -m pip $pip_version"
      ;;
    *)
      say FAIL "python3 -m pip is not there: $(clean "$pip_line")"
      if [ -z "$work" ]; then
        say FAIL "python3 -m ensurepip: no work folder to try it in"
      elif message=$(timeout 120 python3 -m ensurepip --root "$work/ensurepip" 2>&1); then
        site=$(python3 -c 'import sys, sysconfig; print(sys.argv[1] + sysconfig.get_paths()["purelib"])' "$work/ensurepip" 2> /dev/null)
        pip_line=$(PYTHONPATH="$site" python3 -m pip --version 2>&1 | head -n 1)
        case "$pip_line" in
          "pip "[0-9]*)
            pip_version=${pip_line#pip }
            pip_version=${pip_version%% *}
            pip_ok=1
            pip_python_path=$site
            say ok "python3 -m ensurepip makes pip $pip_version in the work folder"
            ;;
          *) say FAIL "python3 -m ensurepip ran and pip does not start: $(clean "$pip_line")" ;;
        esac
      else
        say FAIL "python3 -m ensurepip: $(clean "$message")"
      fi
      ;;
  esac
fi

# The deploy identity, the one that the workflow signs in as and that holds the right to publish code, signs in with the OpenID Connect token that GitHub issued to this run: a
# federated credential, so that no secret exists. This comes first among the checks that use az, because that token is valid for five minutes and the group took some of them to
# start. The sign-in has a folder of its own for the CLI's state, so that the Operator's sign-in below stays as it is and nothing of this one is left behind (the work folder is
# removed at the end). Without a token it says so, with the reason that the workflow gave, and the rest of the probe goes on.
deploy=0
deploy_dir=""
if [ -z "$federated_token" ]; then
  say FAIL "deploy identity sign-in: no token ($(clean "${PROBE_TOKEN_NOTE:-the workflow sent none}"))"
elif ! have az; then
  say FAIL "deploy identity sign-in: az is not in the image"
elif [ -z "${PROBE_DEPLOY_CLIENT_ID:-}" ] || [ -z "${PROBE_DEPLOY_TENANT_ID:-}" ]; then
  say FAIL "deploy identity sign-in: PROBE_DEPLOY_CLIENT_ID or PROBE_DEPLOY_TENANT_ID is not set"
elif [ -z "$work" ]; then
  say FAIL "deploy identity sign-in: no work folder for the CLI's state"
else
  deploy_dir="$work/azure-deploy"
  if message=$(AZURE_CONFIG_DIR="$deploy_dir" timeout 120 az login --service-principal --username "$PROBE_DEPLOY_CLIENT_ID" --tenant "$PROBE_DEPLOY_TENANT_ID" \
    --federated-token "$federated_token" --allow-no-subscriptions --output none 2>&1); then
    deploy=1
    say ok "az login as the deploy identity with the OpenID Connect token"
  else
    say FAIL "deploy identity sign-in: $(clean "${message//"$federated_token"/<token>}")"
  fi
fi
if [ "$deploy" = 1 ]; then
  if [ -z "${OPERATOR_GROUP:-}" ]; then
    say FAIL "az group show as the deploy identity: OPERATOR_GROUP is not set"
  elif message=$(AZURE_CONFIG_DIR="$deploy_dir" timeout 120 az group show --name "$OPERATOR_GROUP" ${OPERATOR_SUBSCRIPTION:+--subscription "$OPERATOR_SUBSCRIPTION"} \
    --query properties.provisioningState --output tsv 2>&1); then
    say ok "az group show of the project group as the deploy identity"
  else
    say FAIL "az group show as the deploy identity: $(clean "${message//"$federated_token"/<token>}")"
  fi
fi

# The identity signs in, and its Reader role on the project's group works.
login=0
if ! have az; then
  say FAIL "az login: az is not in the image"
elif [ -z "${OPERATOR_CLIENT_ID:-}" ]; then
  say FAIL "az login: OPERATOR_CLIENT_ID is not set"
elif message=$(timeout 120 az login --identity --client-id "$OPERATOR_CLIENT_ID" --allow-no-subscriptions --output none 2>&1); then
  login=1
  say ok "az login --identity"
else
  say FAIL "az login --identity: $(clean "$message")"
fi
if [ "$login" = 1 ]; then
  if [ -z "${OPERATOR_GROUP:-}" ]; then
    say FAIL "az group show: OPERATOR_GROUP is not set"
  elif message=$(timeout 120 az group show --name "$OPERATOR_GROUP" ${OPERATOR_SUBSCRIPTION:+--subscription "$OPERATOR_SUBSCRIPTION"} --query properties.provisioningState --output tsv 2>&1); then
    say ok "az group show of the project group: the Reader role works"
  else
    say FAIL "az group show: $(clean "$message")"
  fi
fi

# The resolvers of the container. A container group does not take the DNS servers of the virtual network by itself.
if [ -r "$resolv_conf" ]; then
  resolvers=0
  while read -r key value _; do
    if [ "$key" = nameserver ]; then
      resolvers=$((resolvers + 1))
      if [ "$resolvers" -le 3 ]; then
        if [ "$value" = 168.63.129.16 ]; then
          say ok "resolver $resolvers is the Azure-provided DNS"
        else
          say ok "resolver $resolvers is $(class_of "$value")"
        fi
      fi
    fi
  done < "$resolv_conf"
  if [ "$resolvers" -eq 0 ]; then
    say FAIL "no resolver in /etc/resolv.conf"
  fi
else
  say FAIL "no /etc/resolv.conf"
fi

# Host names, with getent: the way a program of the image resolves them.
for name in ${PROBE_NAMES:-}; do
  if [ "$full" = 1 ]; then
    break
  fi
  case "$name" in
    *[!A-Za-z0-9._-]*) say FAIL "dns: not a host name, skipped"; continue ;;
  esac
  if ! have getent; then
    say FAIL "dns $name: getent is not in the image"
    continue
  fi
  address=$(timeout 20 getent ahostsv4 "$name" 2> /dev/null | { read -r first _; printf '%s' "$first"; })
  if [ -z "$address" ]; then
    say FAIL "dns $name does not resolve"
    continue
  fi
  kind=$(class_of "$address")
  expected=0
  for private_name in ${PROBE_PRIVATE_NAMES:-}; do
    if [ "$private_name" = "$name" ]; then
      expected=1
    fi
  done
  if [ "$expected" = 1 ] && [ "$kind" != private ]; then
    say FAIL "dns $name is $kind, a private address was expected"
  else
    say ok "dns $name is $kind"
  fi
done

# Addresses over https: reachable means that the server answered, whatever the status; the status is said. Redirects are followed twice at most.
for url in ${PROBE_URLS:-}; do
  if [ "$full" = 1 ]; then
    break
  fi
  case "$url" in
    https://*) ;;
    *) say FAIL "url is not an https address, skipped"; continue ;;
  esac
  host=${url#https://}
  host=${host%%/*}
  case "$host" in
    "" | *[!A-Za-z0-9.:-]*) say FAIL "url has an odd host name, skipped"; continue ;;
  esac
  if ! have curl; then
    say FAIL "https $host: curl is not in the image"
    continue
  fi
  result=$(curl --silent --output /dev/null --location --max-redirs 2 --max-time 10 --write-out '%{http_code} %{url_effective}' "$url" 2> /dev/null)
  status=$?
  code=${result%% *}
  final=${result#* }
  final=${final#https://}
  final=${final%%/*}
  if [ "$status" = 0 ]; then
    if [ "$final" != "$host" ] && [ -n "$final" ]; then
      say ok "https $host $code -> $final"
    else
      say ok "https $host $code"
    fi
  elif [ "$status" = 47 ]; then
    say ok "https $host answers, with more than 2 redirects"
  else
    say FAIL "https $host $(why "$status") (curl $status)"
  fi
done

# The secret volume carries files of any size up to a limit that the documentation does not state: this is where it is measured.
if [ -e "$volume/size-test" ]; then
  bytes=$(wc -c < "$volume/size-test" | tr -d ' ')
  if [ -z "${PROBE_SIZE_BYTES:-}" ]; then
    say ok "secret volume file is $bytes bytes"
  elif [ "$bytes" = "$PROBE_SIZE_BYTES" ]; then
    say ok "secret volume file is $bytes bytes, as sent"
  else
    say FAIL "secret volume file is $bytes bytes, $PROBE_SIZE_BYTES were sent"
  fi
elif [ -n "${PROBE_SIZE_BYTES:-}" ]; then
  say FAIL "no size-test file in the secret volume"
fi

# The deployment sites of the function apps (<app>.scm.azurewebsites.net): the address that the name resolves to, private or public, and the status of an unauthenticated GET of /,
# which is a status and no content. A private address with an answer means that the app's private endpoint works from this group: the endpoint is up and the landing zone's policy has
# registered the name in its central zone. The status is whatever the site says without a sign-in (no redirect is followed), and what it means is not read into it here.
for host in ${PROBE_SCM_HOSTS:-}; do
  if [ "$full" = 1 ]; then
    break
  fi
  case "$host" in
    "" | *[!A-Za-z0-9.-]*) say FAIL "scm: not a host name, skipped"; continue ;;
  esac
  app=${host%%.*}
  if ! have getent || ! have curl; then
    say FAIL "scm $app: getent or curl is not in the image"
    continue
  fi
  address=$(timeout 20 getent ahostsv4 "$host" 2> /dev/null | { read -r first _; printf '%s' "$first"; })
  if [ -z "$address" ]; then
    say FAIL "scm $app: the name does not resolve"
    continue
  fi
  kind=$(class_of "$address")
  expected=0
  for private_name in ${PROBE_PRIVATE_NAMES:-}; do
    if [ "$private_name" = "$host" ]; then
      expected=1
    fi
  done
  code=$(curl --silent --output /dev/null --max-time 20 --write-out '%{http_code}' "https://$host/" 2> /dev/null)
  status=$?
  if [ "$status" != 0 ]; then
    say FAIL "scm $app: $kind address, GET / $(why "$status") (curl $status)"
  elif [ "$expected" = 1 ] && [ "$kind" != private ]; then
    say FAIL "scm $app: $kind address, expected private; GET / gives $code"
  else
    say ok "scm $app: $kind address, GET / gives $code"
  fi
done

# The cases app's libraries, built here from the lock file that came in the secret volume: the pip command of tools/build-function-app.sh (the same flags in the same order) for the
# app's runtime, Python 3.13 on Linux, although the Python of this image is another one. It is tried as the script runs it first. pip checks the Requires-Python of a library
# against the version that it is told to build for, and whether that is enough is what the first attempt shows. If it fails for a reason that --ignore-requires-python can change, the
# second attempt adds that flag, which is safe only because every version is pinned and every file is checked against its hash (--require-hashes). A failure of the network, of the
# certificate or of a hash is not tried again. What is built is counted and then removed: the work folder goes at the end in any case.
lock="$volume/cases-requirements.txt"
build_dir="$work/cases/.python_packages/lib/site-packages"
build_output=""
build_status=0
build_seconds=0

# One run of the command, with $1 an extra flag or nothing. The target does not exist before, as in the script.
build_once() {
  rm -rf "$work/cases"
  SECONDS=0
  build_output=$(PIP_CACHE_DIR="$work/pip-cache" timeout 240 env ${pip_python_path:+"PYTHONPATH=$pip_python_path"} python3 -m pip install --quiet --disable-pip-version-check \
    --no-compile --only-binary=:all: --require-hashes \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --implementation cp --python-version 3.13 $1 \
    --target "$build_dir" --requirement "$lock" 2>&1)
  build_status=$?
  build_seconds=$SECONDS
}

# The reason, in a few words, of the attempt that was made last.
build_reason() {
  if [ "$build_status" = 124 ]; then
    echo "timed out after 240 s"
  else
    pip_reason "$build_output"
  fi
}

if [ "$full" = 1 ]; then
  : # the output is full: nothing more can be said, so nothing more is built
elif [ ! -e "$lock" ]; then
  say FAIL "no cases-requirements.txt in the secret volume"
else
  lock_bytes=$(wc -c < "$lock" | tr -d ' ')
  if [ -z "${PROBE_LOCK_BYTES:-}" ]; then
    say ok "cases lock file is $lock_bytes bytes"
  elif [ "$lock_bytes" = "$PROBE_LOCK_BYTES" ]; then
    say ok "cases lock file is $lock_bytes bytes, as sent"
  else
    say FAIL "cases lock file is $lock_bytes bytes, $PROBE_LOCK_BYTES were sent"
  fi
  if [ "$pip_ok" != 1 ]; then
    say FAIL "cases build skipped: there is no pip"
  elif [ -z "$work" ]; then
    say FAIL "cases build skipped: no work folder"
  else
    build_once ""
    if [ "$build_status" = 0 ]; then
      say ok "cases build needs no --ignore-requires-python: $(stats "$work/cases"), $build_seconds s, hashes ok"
    else
      reason=$(build_reason)
      case "$reason" in
        "a hash does not"* | "pip does not trust"* | "a name was not"* | "the connection failed" | "timed out"*)
          say FAIL "cases build: $reason"
          ;;
        *)
          say FAIL "cases build without --ignore-requires-python: $reason"
          build_once "--ignore-requires-python"
          if [ "$build_status" = 0 ]; then
            say ok "cases build only with --ignore-requires-python: $(stats "$work/cases"), $build_seconds s, hashes ok"
          else
            say FAIL "cases build with --ignore-requires-python too: $(build_reason)"
          fi
          ;;
      esac
    fi
    rm -rf "$work/cases" "$work/pip-cache"
  fi
fi

exit 0
