#!/bin/bash
# Publishes the code of the cases function app (the web page and the Watch) from inside the network, as the deploy identity (docs/proposals/07-private-by-default.md, phase 2).
#
# Once the function app has no public endpoint, the workflow's runner can no longer reach its deployment site (<app>.scm.azurewebsites.net). So the code is published from a
# short-lived container group in the project's virtual network, through the app's private endpoint. tools/operator-run.py makes the group, puts this script and the files below into the
# secret volume at /mnt/op, and reads the log. The container signs in as the DEPLOY IDENTITY, the one that the workflow signs in as and that holds the right to write to the app, with the
# OpenID Connect token that GitHub issued to the run: a federated credential, so that no key, no password and no publish profile exists (AGENTS.md rule 23). It does not sign in as the
# Operator: the Operator's own identity holds no right that writes (rule 29), and the publish needs none.
#
# The image is mcr.microsoft.com/azure-cli (bash, az, python3 3.12, curl, getent and the coreutils). It has no pip, no zip, no unzip and no find that anything may rely on, so pip is made by
# ensurepip in a work folder, and Python opens and makes the zip files. A container group's request takes only a few hundred kilobytes of files (tools/operator-run.py, MAX_FILE_BYTES, has the
# evidence), and the app's package is not that small (614,068 bytes), so no package travels in it. The workflow sends the app's sources (cases-source.zip, made by tools/build-function-app.sh with
# FUNCTION_APP_SOURCES_ONLY=1) and that same script (build-function-app.sh), and the libraries are built here from the hash-locked requirements.txt in the sources, with the one pip command of
# that script (FUNCTION_APP_BUILD_IN_OPERATOR=1). The app runs on the plan that PUBLISH_PLAN names, and the package is published the way that plan needs:
#   Flex    the Flex Consumption app: `az functionapp deployment source config-zip` of the built package, as the runner ran it before the publish moved into the network
#   Basic   the built package is posted to the deployment site's zip deployment, with curl, as the runner did
# (The usage app, which was the other app published here, was removed on 2026-11-07 with the usage recording; the action retire-old deletes what is left of it.)
#
# What it reads, all from the environment (none of it is a secret, except the one that says so):
#   PUBLISH_KIND            cases (the only app that is published here now)
#   PUBLISH_PLAN            Flex or Basic: the plan that the app runs on (the workflow passes CASES_APP_PLAN of tools/environment-params.py). Optional: empty is Basic.
#   PUBLISH_APP             the name of the function app
#   PUBLISH_RESOURCE_GROUP  the app's resource group
#   PUBLISH_SUBSCRIPTION    the subscription of that group
#   PUBLISH_CLIENT_ID, PUBLISH_TENANT_ID
#                           the deploy identity and its tenant: az login --service-principal --federated-token
#   AZURE_FEDERATED_TOKEN   THE ONE SECRET: the OpenID Connect token that GitHub issued to the run (audience api://AzureADTokenExchange, valid for five minutes), sent as a secure environment
#                           variable. It is read once at the start and taken out of the environment, so that nothing that runs below inherits it, and it is never printed: it is handed to the
#                           az login of the deploy identity and to nothing else
#   PUBLISH_FILE_BYTES      the size that the main file of the secret volume (cases-source.zip) was sent with: a file that arrived short is never published
#   PUBLISH_HOLD_SECONDS    optional, 0 to 60, default 20: how long the container stays after the work, so that the tool that reads the log through Azure Resource Manager can read the whole of it
#   PUBLISH_VOLUME          where the secret volume is mounted (default /mnt/op); PUBLISH_TMP where the work folder is made (default /tmp): both only for the tests
#
# It prints a few short lines of its own ("ok:" or "FAIL:"), then at most a few lines of what a failed command said, and at last "publish-done: exit code N". Anything that looks like a token is
# hidden in what a command said, and a value that was given to it is never printed back. The exit code: 0 published; 1 the publish itself failed after its attempts; 2 the input was refused and
# nothing was run; 3 the container could not do it (a program is missing, a name does not resolve to a private address, the sign-in or the build failed). The work folder is removed at the end.
LC_ALL=C
export LC_ALL
set -u
set -f
export AZURE_CORE_COLLECT_TELEMETRY=false AZURE_CORE_NO_COLOR=true AZURE_CORE_ONLY_SHOW_ERRORS=true AZURE_CORE_LOGIN_EXPERIENCE_V2=off PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
volume=${PUBLISH_VOLUME:-/mnt/op}
tmp_root=${PUBLISH_TMP:-/tmp}

# The token is read once and taken out of the environment: no command below inherits it, and it is used for one thing, the sign-in as the deploy identity.
federated_token=${AZURE_FEDERATED_TOKEN:-}
unset AZURE_FEDERATED_TOKEN
arm_token=""

# A folder of its own for the Azure CLI's state, the sources, the build and the pip made by ensurepip, removed at the end whatever happens.
work=""
finish() {
  local code=$?
  case "$work" in
    "$tmp_root"/publish-?*) rm -rf "$work" ;;
  esac
  printf 'publish-done: exit code %s\n' "$code"
}
trap finish EXIT

say() {
  printf '%s: %s\n' "$1" "${2:0:160}"
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

# The first lines of what a command said (at most $2), each cut to 160 characters, with the tokens that this script holds taken out and anything that looks like a token hidden.
quote() {
  local text=$1
  text=${text//"$federated_token"/<token>}
  if [ -n "$arm_token" ]; then
    text=${text//"$arm_token"/<token>}
  fi
  printf '%s\n' "$text" | tr -c '[:print:]\n' ' ' \
    | sed -E 's|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*|<token hidden>|g; s|([Bb]earer +)[A-Za-z0-9._~+/=-]{20,}|\1<token hidden>|g' \
    | cut -c1-160 | head -n "$2" | sed -E 's|^|  |'
}

# private (10., 172.16 to 172.31, 192.168.) or public, for a dotted IPv4 address
class_of() {
  case "$1" in
    10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) echo private ;;
    *) echo public ;;
  esac
}

# The input is checked before anything runs, and a value is never printed back: it may be anything.
guid='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
app_name='^[A-Za-z0-9][A-Za-z0-9-]{0,58}[A-Za-z0-9]$'
group_name='^[A-Za-z0-9._()-]{1,90}$'
number='^[0-9]{1,9}$'
seconds='^[0-9]{1,2}$'
token_characters='^[A-Za-z0-9._~+/=-]+$'

# A token is 20 to 8,000 of those characters (a repetition count of that size is not one that every regular expression library of bash takes, so the length is counted apart).
looks_like_a_token() {
  [[ $1 =~ $token_characters ]] && [ "${#1}" -ge 20 ] && [ "${#1}" -le 8000 ]
}

kind=${PUBLISH_KIND:-}
case "$kind" in
  cases) ;;
  *) refuse "PUBLISH_KIND is cases" ;;
esac
plan=${PUBLISH_PLAN:-}
if [ -z "$plan" ]; then
  plan=Basic
fi
case "$plan" in
  Flex | Basic) ;;
  *) refuse "PUBLISH_PLAN is Flex or Basic" ;;
esac
app=${PUBLISH_APP:-}
[[ $app =~ $app_name ]] || refuse "PUBLISH_APP is not the name of a function app"
group=${PUBLISH_RESOURCE_GROUP:-}
[[ $group =~ $group_name ]] || refuse "PUBLISH_RESOURCE_GROUP is not the name of a resource group"
subscription=${PUBLISH_SUBSCRIPTION:-}
[[ $subscription =~ $guid ]] || refuse "PUBLISH_SUBSCRIPTION is not a subscription id"
client_id=${PUBLISH_CLIENT_ID:-}
[[ $client_id =~ $guid ]] || refuse "PUBLISH_CLIENT_ID is not the client id of an identity"
tenant_id=${PUBLISH_TENANT_ID:-}
[[ $tenant_id =~ $guid ]] || refuse "PUBLISH_TENANT_ID is not a tenant id"
looks_like_a_token "$federated_token" || refuse "AZURE_FEDERATED_TOKEN is not set, or is not made of the characters of a token"
sent_bytes=${PUBLISH_FILE_BYTES:-}
[[ $sent_bytes =~ $number ]] || refuse "PUBLISH_FILE_BYTES is not the size of the file that was sent"
hold=${PUBLISH_HOLD_SECONDS:-20}
[[ $hold =~ $seconds ]] && [ "$hold" -le 60 ] || refuse "PUBLISH_HOLD_SECONDS is a number from 0 to 60"
main_file="$volume/cases-source.zip"
[ -f "$volume/build-function-app.sh" ] || refuse "build-function-app.sh is not in the secret volume"
[ -f "$main_file" ] || refuse "${main_file##*/} is not in the secret volume"

missing=""
programs="az python3 timeout sed getent"
if [ "$plan" = Basic ]; then
  programs="$programs curl"
fi
for program in $programs; do
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
if ! work=$(mktemp -d "$tmp_root/publish-XXXXXX" 2> /dev/null); then
  work=""
  say FAIL "no work folder to publish from"
  exit 3
fi
export AZURE_CONFIG_DIR="$work/azure"

# The file that carries the code arrived whole, or nothing is published: sources that are cut short would be a broken app.
bytes=$(wc -c < "$main_file" | tr -d ' ')
if [ "$bytes" != "$sent_bytes" ]; then
  say FAIL "${main_file##*/} is $bytes bytes, $sent_bytes were sent"
  exit 3
fi
say ok "${main_file##*/} is $bytes bytes, as sent"

# The deploy identity signs in first, because its token is valid for five minutes and the group took some of them to start. Three tries, because the first minute of a group can be noisy.
login=0
for attempt in 1 2 3; do
  if message=$(timeout 120 az login --service-principal --username "$client_id" --tenant "$tenant_id" --federated-token "$federated_token" --allow-no-subscriptions --output none 2>&1); then
    login=1
    break
  fi
  if [ "$attempt" -lt 3 ]; then
    sleep 10
  fi
done
if [ "$login" != 1 ]; then
  say FAIL "az login as the deploy identity: $(clean "${message//"$federated_token"/<token>}")"
  exit 3
fi
say ok "az login as the deploy identity with the OpenID Connect token"
if message=$(timeout 120 az account set --subscription "$subscription" 2>&1); then
  say ok "az account set"
else
  say FAIL "az account set: $(clean "${message//"$federated_token"/<token>}")"
  exit 3
fi

# The Azure CLI gets every new token with the sign-in's assertion, the OpenID Connect token, which is valid for five minutes: the sign-in was only the first exchange. The start of the group, pip and
# the build come before the publish, so the token that the publish needs is fetched now, while the assertion is fresh, and the CLI finds it in its cache. It is the lesson of the Hub's new sign-in
# before each publish.
if [ "$plan" = Flex ]; then
  # On a Flex Consumption app `az functionapp deployment source config-zip` asks Microsoft Entra for one more token, for the App Service resource (read in the Azure CLI's development source, not in
  # 2.92.0). A failure is said and does not stop the run: the publish says what it needs.
  if message=$(timeout 120 az account get-access-token --resource https://appservice.azure.com --output none 2>&1); then
    say ok "az token for the App Service resource, fetched while the OpenID Connect token is fresh"
  else
    say FAIL "az token for the App Service resource (the publish goes on): $(clean "${message//"$federated_token"/<token>}")"
  fi
else
  # The package goes to the app's deployment site (Kudu's zip deployment) with the signed-in identity's token for Azure Resource Manager, which is how Microsoft documents a zip deployment to a site
  # whose basic authentication is off. The token is held in a variable, it is on no command line (curl reads the header from a configuration on standard input), and it is hidden in what is printed.
  if arm_token=$(timeout 120 az account get-access-token --resource https://management.azure.com --query accessToken --output tsv 2> "$work/token.err") && looks_like_a_token "$arm_token"; then
    say ok "az account get-access-token for Azure Resource Manager"
  else
    say FAIL "az account get-access-token: $(clean "$(cat "$work/token.err" 2> /dev/null)")"
    arm_token=""
    exit 3
  fi
fi

# The point of publishing from here is the private endpoint of the app: both names of the app have to resolve to a private address, which they do once the landing zone's policy has registered
# them in its central zone (the workflow waits for that). A name that is public, or that does not resolve, would make the publish go the public way, which proves nothing, or end the deployment
# with "Reset all workers endpoint responded with Name or service not known". The first minute of a group can be noisy, so a name is tried three times.
for host in "$app.scm.azurewebsites.net" "$app.azurewebsites.net"; do
  verdict=""
  for attempt in 1 2 3; do
    address=$(timeout 20 getent ahostsv4 "$host" 2> /dev/null | { read -r first _; printf '%s' "$first"; })
    if [ -z "$address" ]; then
      verdict="does not resolve"
    elif [ "$(class_of "$address")" != private ]; then
      verdict="resolves to a public address"
    else
      verdict=""
      break
    fi
    if [ "$attempt" -lt 3 ]; then
      sleep 10
    fi
  done
  if [ -n "$verdict" ]; then
    say FAIL "$host $verdict: the private endpoint's name is not registered (yet)"
    exit 3
  fi
  say ok "$host resolves to a private address"
done

# pip, for the build of the apps' libraries: the image has none, and ensurepip makes one in the work folder (the system's Python is not changed).
make_pip() {
  local line site version
  pip_python_path=""
  line=$(python3 -m pip --version 2>&1 | head -n 1)
  case "$line" in
    "pip "[0-9]*)
      version=${line#pip }
      say ok "python3 -m pip ${version%% *}"
      return 0
      ;;
  esac
  if ! message=$(timeout 120 python3 -m ensurepip --root "$work/ensurepip" 2>&1); then
    say FAIL "python3 -m ensurepip: $(clean "$message")"
    return 1
  fi
  site=$(python3 -c 'import sys, sysconfig; print(sys.argv[1] + sysconfig.get_paths()["purelib"])' "$work/ensurepip" 2> /dev/null)
  line=$(PYTHONPATH="$site" python3 -m pip --version 2>&1 | head -n 1)
  case "$line" in
    "pip "[0-9]*)
      pip_python_path=$site
      version=${line#pip }
      say ok "python3 -m ensurepip makes pip ${version%% *} in the work folder"
      return 0
      ;;
  esac
  say FAIL "python3 -m ensurepip ran and pip does not start: $(clean "$line")"
  return 1
}

# "12.3" for a number of bytes, in megabytes
megabytes() {
  printf '%s.%s' "$(($1 / 1048576))" "$((($1 % 1048576) * 10 / 1048576))"
}

# The sources that came in the secret volume are unpacked, and the package is built from them by the script of the repository in the Operator's mode: one pip command and one layout for both apps
# (tools/build-function-app.sh). $1 is the app's directory under src, $2 the name of its code package, $3 what the package is called here (cases). The built zip is $package_zip. A build is
# tried twice, because the first minute of a group can be noisy and what it fetches comes from the network; a lock that does not match its hashes fails twice, and says so.
build_package() {
  local app_directory=$1 package_name=$2 label=$3 attempt built=0 zip_bytes
  make_pip || return 3
  if ! message=$(python3 -c '
import os, sys, zipfile
target = os.path.realpath(sys.argv[2])
with zipfile.ZipFile(sys.argv[1]) as archive:
    for member in archive.infolist():
        path = os.path.realpath(os.path.join(target, member.filename))
        if path != target and not path.startswith(target + os.sep):
            sys.exit("a file of the sources would be unpacked outside the folder")
    archive.extractall(target)
    print(len(archive.namelist()))
' "$main_file" "$work/source" 2>&1); then
    say FAIL "the sources could not be unpacked: $(clean "$message")"
    return 3
  fi
  say ok "the sources are unpacked: $message files"
  for attempt in 1 2; do
    SECONDS=0
    if build_output=$(env FUNCTION_APP_SOURCE_DIR="$work/source" FUNCTION_APP_BUILD_IN_OPERATOR=1 PIP_CACHE_DIR="$work/pip-cache" ${pip_python_path:+"PYTHONPATH=$pip_python_path"} \
      timeout 300 bash "$volume/build-function-app.sh" "$app_directory" "$package_name" "$work/build" "$work/$label.zip" 2>&1); then
      built=1
      break
    fi
    say FAIL "the build of the libraries failed (attempt $attempt of 2)"
    quote "$build_output" 6
    rm -rf "$work/build" "$work/$label.zip" "$work/pip-cache"
    if [ "$attempt" -lt 2 ]; then
      sleep 15
    fi
  done
  if [ "$built" != 1 ]; then
    return 3
  fi
  package_zip="$work/$label.zip"
  zip_bytes=$(wc -c < "$package_zip" | tr -d ' ')
  say ok "the $label package is built: $(clean "$(printf '%s\n' "$build_output" | tail -n 1)"), $(megabytes "$zip_bytes") MB zipped, $SECONDS s, hashes ok"
  # The SHA-256 of the exact package that is published next: the record of what went to the app (the summary of the run that sent it keeps this line). A zip holds the time of each file, so it differs from run to
  # run: the digest of the app's own files (PACKAGE_SHA256, tools/source-digest.py) is what is compared with main, and this one says which bytes this run published.
  say ok "the $label package that is published has the SHA-256 $(sha256sum "$package_zip" | cut -d ' ' -f 1)"
  rm -rf "$work/pip-cache" "$work/build" "$work/source"
}

# The Flex Consumption app: the package is built here ($1 is the app's directory under src, $2 the name of its code package, $3 what the package is called here) and published with the
# command that the runner ran before the publish moved into the network, with the same flags and the same attempts. The web page's app is published this way while it runs on Flex Consumption.
publish_flex() {
  local app_directory=$1 package_name=$2 label=$3 attempt
  # The version of the CLI that does the publish is said, because what `config-zip` does for a Flex Consumption app depends on it (the image is pinned by its digest).
  say ok "az $(timeout 60 az version --query '"azure-cli"' --output tsv 2> /dev/null | head -n 1 | tr -cd '0-9A-Za-z.-' | cut -c1-20)"
  build_package "$app_directory" "$package_name" "$label" || return 3
  # A site that has just been made may need a minute before it takes a package.
  for attempt in 1 2 3; do
    if message=$(timeout 600 az functionapp deployment source config-zip --resource-group "$group" --name "$app" --src "$package_zip" --build-remote false --only-show-errors --output none 2>&1); then
      say ok "the $label package is published to $app (attempt $attempt of 3)"
      return 0
    fi
    say FAIL "the publish did not go through (attempt $attempt of 3)"
    quote "$message" 8
    if [ "$attempt" -lt 3 ]; then
      sleep 60
    fi
  done
  say FAIL "the code could not be published to $app"
  return 1
}

publish_cases() {
  local attempt code
  build_package case-functions cases cases || return 3
  # The built package goes to the app's deployment site (Kudu's zip deployment) with the token of Azure Resource Manager that was fetched at the start. A site that has just been made may need a few
  # minutes. The package is in the work folder of the container, so no limit of the request applies to it.
  for attempt in 1 2 3 4 5; do
    code=$(printf 'header = "Authorization: Bearer %s"\n' "$arm_token" | curl --config - --silent --show-error --output "$work/zipdeploy.txt" --write-out '%{http_code}' --max-time 900 \
      --request POST --header 'Content-Type: application/zip' --data-binary "@$package_zip" "https://$app.scm.azurewebsites.net/api/zipdeploy" || echo "000")
    code=${code:0:3}
    if [ "$code" = 200 ] || [ "$code" = 202 ]; then
      say ok "the deployment site took the package (HTTP $code, attempt $attempt of 5)"
      return 0
    fi
    say FAIL "the publish was answered with HTTP $code (attempt $attempt of 5)"
    quote "$(head -c 300 "$work/zipdeploy.txt" 2> /dev/null)" 3
    if [ "$attempt" -lt 5 ]; then
      sleep 60
    fi
  done
  say FAIL "the code could not be published to $app"
  return 1
}

if [ "$plan" = Flex ]; then
  publish_flex case-functions cases cases
  code=$?
else
  publish_cases
  code=$?
fi
# The log of a stopped container keeps only its last 16 KB, and the tool that reads it through Azure Resource Manager polls every few seconds while the container runs: the hold lets it read the whole log.
if [ "$hold" -gt 0 ]; then
  sleep "$hold"
fi
exit "$code"
