#!/bin/bash
# The probe of the Operator: what a container in the Operator's subnet can do, said in short lines (docs/proposals/07-private-by-default.md).
#
# It runs inside the container that tools/operator-run.py makes in the Operator's subnet, with the image mcr.microsoft.com/azure-cli (bash, az, python3, curl and
# getent; no jq and no awk are assumed). It prints at most 120 short lines, one "ok:" or "FAIL:" line for each check, and never a token, a key or a secret: what a
# command says is cut to a few words, and ids and long strings in it are hidden. The log of a stopped container is cut at 16 KB or 1,000 lines, so the probe stays far
# below both. The last line is always "probe-done", and the exit code is always 0: the facts are the product, and a failed check is a line, not a failure of the run.
#
# What it reads, all from the environment (none of it is a secret):
#   OPERATOR_CLIENT_ID     client id of the user-assigned identity: az login --identity --client-id
#   OPERATOR_GROUP         the project's resource group, read with the identity's token
#   OPERATOR_SUBSCRIPTION  optional: the subscription of that group, when the login does not find it by itself
#   PROBE_NAMES            host names to look up, separated by spaces; each is said private or public
#   PROBE_PRIVATE_NAMES    optional: the names among them that must resolve to a private address (a public answer is then a FAIL)
#   PROBE_URLS             https addresses to reach, separated by spaces: the status code, or what went wrong (at most two redirects are followed)
#   PROBE_SIZE_BYTES       the size that /mnt/op/size-test was sent with, when the secret volume carries that file
#   PROBE_VOLUME           where the secret volume is mounted (default /mnt/op); PROBE_RESOLV_CONF the resolver file (default /etc/resolv.conf): both only for the tests
LC_ALL=C
export LC_ALL
set -u
set -f
export AZURE_CORE_COLLECT_TELEMETRY=false AZURE_CORE_NO_COLOR=true AZURE_CORE_ONLY_SHOW_ERRORS=true AZURE_CORE_LOGIN_EXPERIENCE_V2=off
volume=${PROBE_VOLUME:-/mnt/op}
resolv_conf=${PROBE_RESOLV_CONF:-/etc/resolv.conf}

MAX_LINES=120
printed=0
full=0
trap 'printf "probe-done\n"; exit 0' EXIT

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

exit 0
