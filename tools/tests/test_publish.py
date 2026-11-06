import hashlib
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def posix(path):
    result = Path(path).resolve().as_posix()
    if os.name == "nt" and len(result) > 1 and result[1] == ":":
        return "/" + result[0].lower() + result[2:]
    return result


APP = "func-meternaut-usage-0a1b2c3d"
CASES_APP = "func-meternaut-cases-0a1b2c3d"
GROUP = "rg-of-the-project"
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
DEPLOY_CLIENT = "aaaaaaaa-1111-2222-3333-444444444444"
DEPLOY_TENANT = "bbbbbbbb-5555-6666-7777-888888888888"
FEDERATED_TOKEN = "fake-oidc-token-Q9x7LmN2pR5tV8wY"
ARM_TOKEN = "fake-arm-token-Z3k8TnW1qL6vB4xC9y"
A_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvOm9yZy9uYW1lIn0.c2lnbmF0dXJlLW9mLWEtdG9rZW4"

# Stand-ins for what operator/publish.sh calls. Every call of az, python3 -m, curl and sleep is written to FAKE_LOG, so that a test sees what was called and in what order. The script is run with the
# folder of the stand-ins first on the path inside its own shell, so that a command that Git's bash has of its own (sleep, curl) is replaced too.
STUB_AZ = """#!/bin/bash
# stand-in for az. FAKE_AZ_LOGIN, FAKE_AZ_ACCOUNT, FAKE_AZ_TOKEN and FAKE_AZ_DEPLOY say how each ends: ok, fail (every time), once or twice (the first one or two calls fail and the next works); FAKE_AZ_TOKEN is
# also odd (an answer that is no token). FAKE_TOKEN_IN_ERROR is what a failed call repeats in its message: the tokens that the script holds. Every call is logged with the folder of the CLI's state, and
# a call that finds the federated token in its environment says so.
echo "az $* [config=${AZURE_CONFIG_DIR:-none}]" >> "$FAKE_LOG"
if [ -n "${AZURE_FEDERATED_TOKEN:-}" ]; then echo "az SAW THE TOKEN IN ITS ENVIRONMENT" >> "$FAKE_LOG"; fi
fails() {
  # $1 is the mode, $2 the pattern of the logged calls that are counted
  local calls
  calls=$(grep -c "^az $2" "$FAKE_LOG")
  case "$1" in
    ok) return 1 ;;
    fail) return 0 ;;
    once) [ "$calls" -le 1 ] ;;
    twice) [ "$calls" -le 2 ] ;;
    *) return 1 ;;
  esac
}
case "$1 $2" in
  "login --service-principal")
    if fails "${FAKE_AZ_LOGIN:-ok}" "login"; then
      echo "ERROR: AADSTS70021: the assertion ${FAKE_TOKEN_IN_ERROR:-} was refused, no matching federated identity record" >&2
      echo "second line that must not show" >&2
      exit 1
    fi
    exit 0 ;;
  "account set")
    if fails "${FAKE_AZ_ACCOUNT:-ok}" "account set"; then echo "ERROR: The subscription of '$4' doesn't exist." >&2; exit 1; fi
    exit 0 ;;
  "account get-access-token")
    case "${FAKE_AZ_TOKEN:-ok}" in
      ok) printf '%s\\n' "$FAKE_ARM_TOKEN"; exit 0 ;;
      odd) echo "this is not a token"; exit 0 ;;
      *) echo "ERROR: Please run 'az login' to setup account. ${FAKE_TOKEN_IN_ERROR:-}" >&2; exit 1 ;;
    esac ;;
  "functionapp deployment")
    if fails "${FAKE_AZ_DEPLOY:-ok}" "functionapp deployment"; then
      echo "ERROR: Zip deployment failed. Deployment was successful but Reset all workers endpoint responded with Name or service not known ${FAKE_TOKEN_IN_ERROR:-}" >&2
      echo "WARNING: second line of the error" >&2
      for number in 1 2 3 4 5 6 7 8 9 10 11 12; do echo "WARNING: line $number of a long error" >&2; done
      exit 1
    fi
    previous=""
    for argument in "$@"; do
      if [ "$previous" = --src ] && [ -n "${FAKE_POSTED:-}" ]; then cp "$argument" "$FAKE_POSTED"; fi
      previous=$argument
    done
    echo '{"id": "a long document that --output none keeps out of the log"}'
    exit 0 ;;
  "version --query") echo "${FAKE_AZ_VERSION:-2.92.0}"; exit 0 ;;
esac
echo "unexpected az call: $*" >&2
exit 9
"""

STUB_GETENT = """#!/bin/bash
# stand-in for getent: FAKE_DNS is "name=ip name=ip"; a name that is not in it does not resolve. FAKE_DNS_LATE is "name=ip": that name does not resolve at the first try and does at the second
if [ "$1" != ahostsv4 ]; then exit 2; fi
echo "getent $*" >> "$FAKE_LOG"
if [ -n "${FAKE_DNS_LATE:-}" ] && [ "${FAKE_DNS_LATE%%=*}" = "$2" ] && [ "$(grep -c "^getent ahostsv4 $2\\$" "$FAKE_LOG")" -le 1 ]; then exit 2; fi
for pair in ${FAKE_DNS:-} ${FAKE_DNS_LATE:-}; do
  if [ "${pair%%=*}" = "$2" ]; then
    ip=${pair#*=}
    printf '%s      STREAM %s\\n%s      DGRAM\\n%s      RAW\\n' "$ip" "$2" "$ip" "$ip"
    exit 0
  fi
done
exit 2
"""

STUB_CURL = """#!/bin/bash
# stand-in for curl, which the publish of the cases runs: what it was given on the command line, on standard input (the bearer of the request) and as the file to post (its size and its hash, and a copy of it in
# FAKE_POSTED). FAKE_CURL_CODES
# is the status of each call in turn, and the last one goes on for the calls after those. The status is what --write-out prints, and the body goes to the file that --output names.
{ echo "curl $*"; echo "curl-stdin $(cat)"; } >> "$FAKE_LOG"
output=""
previous=""
for argument in "$@"; do
  if [ "$previous" = --output ]; then output=$argument; fi
  if [ "$previous" = --data-binary ]; then
    file=${argument#@}
    echo "curl-file $(wc -c < "$file" | tr -d ' ') $(sha256sum < "$file" | cut -d' ' -f1)" >> "$FAKE_LOG"
    if [ -n "${FAKE_POSTED:-}" ]; then cp "$file" "$FAKE_POSTED"; fi
  fi
  previous=$argument
done
codes=(${FAKE_CURL_CODES:-200})
number=$(grep -c '^curl ' "$FAKE_LOG")
code=${codes[$((number - 1))]:-${codes[$((${#codes[@]} - 1))]}}
if [ -n "$output" ]; then echo "the site said ${FAKE_TOKEN_IN_ERROR:-nothing} with HTTP $code" > "$output"; fi
printf '%s' "$code"
exit "${FAKE_CURL_EXIT:-0}"
"""

STUB_TIMEOUT = """#!/bin/bash
shift
exec "$@"
"""

STUB_SLEEP = """#!/bin/bash
echo "sleep $*" >> "$FAKE_LOG"
"""

STUB_PYTHON = """#!/bin/bash
# stand-in for python3. -c with the guard of the build script exits as FAKE_PYTHON_VERSION says (3.13.x passes); -c with the version of the interpreter says FAKE_PYTHON_VERSION; -c with sysconfig says where
# ensurepip put pip; -m pip --version is FAKE_PIP (ok, or missing: no pip unless PYTHONPATH names the one that ensurepip made); -m ensurepip is FAKE_ENSUREPIP (ok or disabled); -m pip install is a fake
# download that FAKE_PIP says how it ends (ok, foreign: it unpacks a compiled module of another Python, hash, network, first-fails: the first attempt fails and the next works). Every other call is the real
# Python (REAL_PYTHON), with the paths that it is given turned into the paths that it understands.
if [ -n "${FAKE_LOG:-}" ]; then
  if [ "$1" = -m ]; then echo "python3 $* [PYTHONPATH=${PYTHONPATH:-none}]" >> "$FAKE_LOG"; fi
  if [ -n "${AZURE_FEDERATED_TOKEN:-}" ]; then echo "python3 SAW THE TOKEN IN ITS ENVIRONMENT" >> "$FAKE_LOG"; fi
fi
real() {
  local arguments=() argument
  for argument in "$@"; do
    if command -v cygpath > /dev/null 2>&1 && [ "${argument:0:1}" = / ] && { [ -e "$argument" ] || [ -d "$(dirname "$argument")" ]; }; then
      arguments+=("$(cygpath -w "$argument")")
    else
      arguments+=("$argument")
    fi
  done
  exec "$REAL_PYTHON" "${arguments[@]}"
}
case "$1" in
  --version) echo "Python ${FAKE_PYTHON_VERSION:-3.12.7}"; exit 0 ;;
  -c)
    case "$2" in
      *"== (3, 13)"*) case "${FAKE_PYTHON_VERSION:-3.12.7}" in 3.13.*) exit 0 ;; *) exit 1 ;; esac ;;
      *'%d.%d.%d'*) echo "${FAKE_PYTHON_VERSION:-3.12.7}"; exit 0 ;;
      *sysconfig*) echo "$3/usr/lib/python3.12/site-packages"; exit 0 ;;
      *) real "$@" ;;
    esac ;;
  -m)
    case "$2" in
      ensurepip)
        if [ "${FAKE_ENSUREPIP:-ok}" != ok ]; then echo "ERROR: ensurepip is disabled in this Python: install the python3-pip package" >&2; exit 1; fi
        root=""
        previous=""
        for argument in "$@"; do
          if [ "$previous" = --root ]; then root=$argument; fi
          previous=$argument
        done
        mkdir -p "$root/usr/lib/python3.12/site-packages/pip"
        echo "# pip" > "$root/usr/lib/python3.12/site-packages/pip/__init__.py"
        exit 0 ;;
      pip)
        if [ "$3" = --version ]; then
          if [ "${FAKE_PIP:-ok}" = missing ] && [ -z "${PYTHONPATH:-}" ]; then echo "/usr/bin/python3: No module named pip" >&2; exit 1; fi
          echo "pip 25.0.1 from /usr/lib/python3.12/site-packages/pip (python 3.12)"
          exit 0
        fi
        target=""
        previous=""
        for argument in "$@"; do
          if [ "$previous" = --target ]; then target=$argument; fi
          previous=$argument
        done
        case "${FAKE_PIP:-ok}" in
          hash) echo "ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE. ${FAKE_TOKEN_IN_ERROR:-}" >&2; exit 1 ;;
          network) echo "ERROR: Could not find a version that satisfies the requirement azure-core==1.41.0 (Temporary failure in name resolution)" >&2; exit 1 ;;
          first-fails) if [ "$(grep -c '^python3 -m pip install' "$FAKE_LOG")" -le 1 ]; then echo "ERROR: Connection broken by 'ReadTimeoutError'" >&2; exit 1; fi ;;
        esac
        mkdir -p "$target/azure/core" "$target/markupsafe" "$target/cffi"
        echo "# core" > "$target/azure/core/__init__.py"
        head -c 1048576 /dev/urandom > "$target/markupsafe/_speedups.cpython-313-x86_64-linux-gnu.so"
        echo "# abi3 modules carry no tag of an interpreter" > "$target/cffi/_rust.abi3.so"
        if [ "${FAKE_PIP:-ok}" = foreign ]; then echo "# built for 3.12" > "$target/cffi/_cffi_backend.cpython-312-x86_64-linux-gnu.so"; fi
        exit 0 ;;
    esac ;;
  *) real "$@" ;;
esac
echo "unexpected python3 call: $*" >&2
exit 9
"""

USAGE_SOURCE_FILES = {"function_app.py": b"# the app\n", "host.json": b"{}\n", "requirements.txt": b"azure-core==1.41.0 \\\n    --hash=sha256:" + b"ab" * 32 + b"\n",
                      "usage/__init__.py": b"", "usage/jobs.py": b"# jobs\n"}
CASES_SOURCE_FILES = {"function_app.py": b"# the cases app\n", "host.json": b"{}\n", "requirements.txt": b"azure-functions==2.3.0 \\\n    --hash=sha256:" + b"cd" * 32 + b"\n",
                      "cases/__init__.py": b"", "cases/loop.py": b"# loop\n", "cases/web/__init__.py": b"", "cases/web/home.py": b"# home\n"}


def source_zip(files=None):
    """The zip of the sources, as tools/build-function-app.sh makes it with FUNCTION_APP_SOURCES_ONLY=1: the files at its root."""
    path = Path(tempfile.mkdtemp()) / "sources.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in (files or USAGE_SOURCE_FILES).items():
            archive.writestr(name, content)
    data = path.read_bytes()
    shutil.rmtree(path.parent)
    return data


class Ran:
    """What one run of operator/publish.sh did: the process, its lines, the calls that the stand-ins logged, what was left in the work folder, the volume that it was given, whether anything of the
    input was run as a command (a file named canary in the folder that the script ran in), and the package that was published (a copy that the stand-in of az or curl made of the file that it was given)."""

    def __init__(self, done, calls, leftover, volume, canary, posted=None):
        self.done, self.lines, self.calls, self.leftover, self.volume, self.canary, self.posted = done, done.stdout.splitlines(), calls, leftover, volume, canary, posted

    def calls_of(self, prefix):
        return [call for call in self.calls if call.startswith(prefix)]


@unittest.skipIf(BASH is None, "no bash on this machine")
class PublishScript(unittest.TestCase):
    """operator/publish.sh against stand-ins for az, python3, curl, getent, timeout and sleep: what it refuses, what it runs and in what order, what it prints, and that the exit code says how it went."""

    def good_env(self, kind="usage"):
        """Everything that the script is given on the real estate, with stand-ins that answer well. The image has no pip (FAKE_PIP=missing), and both names of the app are private."""
        return {"PUBLISH_KIND": kind, "PUBLISH_APP": APP if kind == "usage" else CASES_APP, "PUBLISH_RESOURCE_GROUP": GROUP, "PUBLISH_SUBSCRIPTION": SUBSCRIPTION, "PUBLISH_CLIENT_ID": DEPLOY_CLIENT,
                "PUBLISH_TENANT_ID": DEPLOY_TENANT, "AZURE_FEDERATED_TOKEN": FEDERATED_TOKEN, "FAKE_ARM_TOKEN": ARM_TOKEN, "FAKE_PIP": "missing",
                "FAKE_DNS": " ".join(f"{app}{suffix}=10.53.0.21" for app in (APP, CASES_APP) for suffix in (".scm.azurewebsites.net", ".azurewebsites.net"))}

    def run_publish(self, env=None, kind="usage", package=None, files=None, stubs=None, sent=None):
        """Runs the script. `package` is the main file that the secret volume carries (None: the usual one for the kind), `files` the other files, `sent` the size that the workflow sent it with."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in {"az": STUB_AZ, "getent": STUB_GETENT, "curl": STUB_CURL, "timeout": STUB_TIMEOUT, "sleep": STUB_SLEEP, "python3": STUB_PYTHON, **(stubs or {})}.items():
                (bin_dir / name).write_text(body, encoding="utf-8", newline="\n")
                (bin_dir / name).chmod(0o755)  # on Linux a file that is not executable is skipped in the search of the path, and the real program would answer
            volume = tmp / "op"
            volume.mkdir()
            main_name = "usage-source.zip" if kind == "usage" else "cases-source.zip"
            content = package if package is not None else source_zip(CASES_SOURCE_FILES if kind == "cases" else None)
            if content is not False:
                (volume / main_name).write_bytes(content)
            (volume / "build-function-app.sh").write_text(text("tools/build-function-app.sh"), encoding="utf-8", newline="\n")
            for name, body in (files or {}).items():
                if body is None:
                    (volume / name).unlink(missing_ok=True)
                else:
                    (volume / name).write_bytes(body)
            work_root = tmp / "work"
            work_root.mkdir()
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            posted = tmp / "posted.zip"
            script = tmp / "publish.sh"
            script.write_text(text("operator/publish.sh"), encoding="utf-8", newline="\n")
            size = len(content) if content is not False else 0
            environment = {**os.environ, "STUBS": posix(bin_dir), "PUBLISH_VOLUME": posix(volume), "PUBLISH_TMP": posix(work_root), "FAKE_LOG": posix(log), "FAKE_POSTED": posix(posted),
                           "REAL_PYTHON": posix(sys.executable), "PUBLISH_FILE_BYTES": str(sent if sent is not None else size), **self.good_env(kind), **(env or {})}
            for name in [name for name, value in environment.items() if value is None]:
                del environment[name]
            done = subprocess.run([BASH, "-c", 'PATH="$STUBS:$PATH"; export PATH; exec bash "$0"', posix(script)], capture_output=True, text=True, env=environment, cwd=tmp)
            return Ran(done, log.read_text(encoding="utf-8").splitlines(), sorted(path.name for path in work_root.iterdir()), posix(volume), (tmp / "canary").exists(),
                       posted.read_bytes() if posted.exists() else None)

    # --- a good run ---------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_good_usage_run_signs_in_first_checks_the_names_builds_the_libraries_here_and_publishes_with_the_command_that_the_runner_ran(self):
        ran = self.run_publish()
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        size = len(source_zip())
        self.assertEqual([re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line) for line in ran.lines], [
            "ok: python3 3.12.7",
            f"ok: usage-source.zip is {size} bytes, as sent",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az account set",
            "ok: az token for the App Service resource, fetched while the OpenID Connect token is fresh",
            f"ok: {APP}.scm.azurewebsites.net resolves to a private address",
            f"ok: {APP}.azurewebsites.net resolves to a private address",
            "ok: az 2.92.0",
            "ok: python3 -m ensurepip makes pip 25.0.1 in the work folder",
            f"ok: the sources are unpacked: {len(USAGE_SOURCE_FILES)} files",
            f"ok: the usage package is built: {len(USAGE_SOURCE_FILES) + 3} files, 1.0 MB zipped, N s, hashes ok",
            f"ok: the usage package is published to {APP} (attempt 1 of 3)",
            "publish-done: exit code 0",
        ])
        az_calls = ran.calls_of("az ")
        self.assertTrue(az_calls[0].startswith("az login --service-principal"), "the sign-in comes before any other call of az")
        self.assertRegex(az_calls[0], rf"^az login --service-principal --username {DEPLOY_CLIENT} --tenant {DEPLOY_TENANT} --federated-token {FEDERATED_TOKEN} --allow-no-subscriptions --output none "
                                      r"\[config=/.+/publish-[^/]+/azure\]$")
        self.assertRegex(ran.calls_of("az account")[0], rf"^az account set --subscription {SUBSCRIPTION} \[config=/.+/publish-[^/]+/azure\]$")
        (deploy,) = ran.calls_of("az functionapp deployment")
        self.assertRegex(deploy, rf"^az functionapp deployment source config-zip --resource-group {GROUP} --name {APP} --src /.+/publish-[^/]+/usage\.zip --build-remote false --only-show-errors --output none ")
        self.assertEqual(ran.leftover, [], "the work folder, with the CLI's state of the deploy identity and what was built, is gone")
        self.assertEqual(ran.calls[-1], "sleep 20", "the container stays after the work so that the log can be read whole")

    def test_the_token_for_the_app_service_resource_is_fetched_right_after_the_sign_in_while_the_assertion_is_fresh_and_only_for_the_usage_app(self):
        # A Flex Consumption app's config-zip asks Microsoft Entra for a token for the App Service resource, the Azure CLI gets every new token with the sign-in's assertion, and that is valid for five
        # minutes (the Hub signs in again before each publish for the same reason): the token is fetched at once, and the CLI finds it in its cache.
        ran = self.run_publish()
        calls = [re.sub(r" \[config=.+\]$", "", call) for call in ran.calls_of("az ")]
        fetch = "az account get-access-token --resource https://appservice.azure.com --output none"
        self.assertEqual(calls[:3], [f"az login --service-principal --username {DEPLOY_CLIENT} --tenant {DEPLOY_TENANT} --federated-token {FEDERATED_TOKEN} --allow-no-subscriptions --output none",
                                     f"az account set --subscription {SUBSCRIPTION}", fetch])
        self.assertLess(calls.index(fetch), min(index for index, call in enumerate(calls) if call.startswith("az functionapp deployment")), "before the build and the publish")
        self.assertEqual(calls.count(fetch), 1)
        ran = self.run_publish(kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual([call for call in ran.calls_of("az ") if "appservice.azure.com" in call], [], "the cases app is published with the token of Azure Resource Manager and nothing else")

    def test_a_token_for_the_app_service_resource_that_cannot_be_had_is_said_with_every_token_hidden_and_the_publish_goes_on(self):
        ran = self.run_publish({"FAKE_AZ_TOKEN": "fail", "FAKE_TOKEN_IN_ERROR": FEDERATED_TOKEN})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        said = [line for line in ran.lines if line.startswith("FAIL: az token for the App Service resource")]
        self.assertEqual(len(said), 1, ran.lines)
        self.assertIn("(the publish goes on)", said[0])
        self.assertLessEqual(len(said[0]), 166)
        self.assertNotIn(FEDERATED_TOKEN, ran.done.stdout + ran.done.stderr)
        self.assertIn(f"ok: the usage package is published to {APP} (attempt 1 of 3)", ran.lines, "the publish says what it needs")

    def test_the_build_is_the_script_of_the_repository_run_in_the_operator_with_the_pip_that_ensurepip_made_and_the_same_flags_as_on_the_runner(self):
        ran = self.run_publish()
        (install,) = [call for call in ran.calls if call.startswith("python3 -m pip install")]
        self.assertRegex(install, r"\[PYTHONPATH=/.+/publish-[^/]+/ensurepip/usr/lib/python3\.12/site-packages\]$", "the pip that ensurepip made is the one that builds")
        self.assertRegex(install, r"--target /.+/publish-[^/]+/build/\.python_packages/lib/site-packages --requirement /.+/publish-[^/]+/source/requirements\.txt ")
        runner = re.search(r"python3 -m pip install (.+?)\n", re.sub(r"\\\n\s*", " ", text("tools/build-function-app.sh"))).group(1)
        flags = [word for word in shlex.split(runner) if word.startswith("--") and not word.startswith(("--target", "--requirement"))]
        for flag in flags:
            self.assertIn(flag, install)
        self.assertIn("--python-version 3.13", install)
        self.assertNotIn("--ignore-requires-python", install, "the strict form, as the probe of the Operator showed that it works")
        (ensure,) = [call for call in ran.calls if call.startswith("python3 -m ensurepip")]
        self.assertRegex(ensure, r"^python3 -m ensurepip --root /.+/publish-[^/]+/ensurepip \[PYTHONPATH=none\]$", "into the work folder, not into the system's Python")

    def test_a_pip_that_the_image_has_is_used_as_it_is(self):
        ran = self.run_publish({"FAKE_PIP": "ok"})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(ran.calls_of("python3 -m ensurepip"), [])
        self.assertIn("ok: python3 -m pip 25.0.1", ran.lines)
        (install,) = [call for call in ran.calls if call.startswith("python3 -m pip install")]
        self.assertTrue(install.endswith("[PYTHONPATH=none]"))

    # What the stand-in of pip puts into the package, besides the sources: three fake libraries (see STUB_PYTHON)
    FAKE_LIBRARIES = [".python_packages/lib/site-packages/azure/core/__init__.py", ".python_packages/lib/site-packages/cffi/_rust.abi3.so",
                      ".python_packages/lib/site-packages/markupsafe/_speedups.cpython-313-x86_64-linux-gnu.so"]

    def members_of_bytes(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return sorted(archive.namelist())

    def test_a_good_cases_run_signs_in_asks_for_the_token_of_resource_manager_builds_the_package_here_and_posts_the_built_package_with_the_bearer_on_standard_input(self):
        ran = self.run_publish(kind="cases")
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        size = len(source_zip(CASES_SOURCE_FILES))
        self.assertEqual([re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line) for line in ran.lines], [
            "ok: python3 3.12.7",
            f"ok: cases-source.zip is {size} bytes, as sent",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az account set",
            "ok: az account get-access-token for Azure Resource Manager",
            f"ok: {CASES_APP}.scm.azurewebsites.net resolves to a private address",
            f"ok: {CASES_APP}.azurewebsites.net resolves to a private address",
            "ok: python3 -m ensurepip makes pip 25.0.1 in the work folder",
            f"ok: the sources are unpacked: {len(CASES_SOURCE_FILES)} files",
            f"ok: the cases package is built: {len(CASES_SOURCE_FILES) + 3} files, 1.0 MB zipped, N s, hashes ok",
            "ok: the deployment site took the package (HTTP 200, attempt 1 of 5)",
            "publish-done: exit code 0",
        ])
        (post,) = ran.calls_of("curl ")
        self.assertRegex(post, rf"--request POST --header Content-Type: application/zip --data-binary @/.+/publish-[^/]+/cases\.zip https://{CASES_APP}\.scm\.azurewebsites\.net/api/zipdeploy")
        self.assertNotIn("cases-source.zip", post, "what is posted is the package that was built in the work folder, and not what came in the volume")
        for flag in ("--config -", "--silent", "--show-error", "--write-out %{http_code}", "--max-time 900"):
            self.assertIn(flag, post)
        self.assertNotIn(ARM_TOKEN, post, "the bearer is on no command line")
        self.assertEqual(ran.calls_of("curl-stdin"), [f'curl-stdin header = "Authorization: Bearer {ARM_TOKEN}"'])
        self.assertEqual(ran.calls_of("curl-file"), [f"curl-file {len(ran.posted)} {hashlib.sha256(ran.posted).hexdigest()}"], "the package is posted whole, byte for byte")
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES), "the sources that came in the volume, and the libraries that were built here")
        self.assertEqual(ran.calls_of("az functionapp"), [], "the cases are published with curl, as the runner did")
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 1, "the package is built here, once")
        self.assertEqual(ran.leftover, [])
        self.assertEqual(ran.calls[-1], "sleep 20")

    def test_the_package_that_az_publishes_for_the_usage_app_is_the_one_that_was_built_here_from_the_sources_in_the_volume(self):
        ran = self.run_publish()
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(USAGE_SOURCE_FILES) + self.FAKE_LIBRARIES))

    def test_the_two_kinds_are_built_by_the_same_command_with_the_same_flags_and_differ_only_in_the_app_that_is_built(self):
        installs = {}
        for kind in ("usage", "cases"):
            ran = self.run_publish(kind=kind)
            (install,) = [call for call in ran.calls if call.startswith("python3 -m pip install")]
            installs[kind] = re.sub(r"/[^ ]*/publish-[^/ ]+/", "<work>/", install)
        self.assertEqual(installs["usage"], installs["cases"], "one pip command, one layout")
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        self.assertIn('build_package usage-functions usage usage || return 3', source)
        self.assertIn('build_package case-functions cases cases || return 3', source)
        self.assertEqual(source.count('timeout 300 bash "$volume/build-function-app.sh"'), 1, "the build is run in one place, for both kinds")
        self.assertEqual(source.count("python3 -m pip install"), 0, "and pip is run by the build script alone")

    # --- the input is refused before anything runs --------------------------------------------------------------------------------------------------------------------------------------

    def refused(self, env, kind="usage", **kwargs):
        ran = self.run_publish(env, kind=kind, **kwargs)
        self.assertEqual(ran.done.returncode, 2, (env, ran.lines))
        self.assertEqual(len(ran.lines), 2, ran.lines)
        self.assertRegex(ran.lines[0], r"^FAIL: ")
        self.assertEqual(ran.lines[1], "publish-done: exit code 2")
        self.assertEqual(ran.calls, [], "nothing runs after a refusal: no sign-in, no name lookup, no build, no sleep")
        self.assertFalse(ran.canary, "nothing of the input was run as a command")
        self.assertEqual(ran.leftover, [], "no work folder was made")
        for value in (env or {}).values():
            if value and len(value) > 8:
                self.assertNotIn(value, ran.done.stdout + ran.done.stderr, "a value is never printed back: it may be anything")
        return ran

    def test_a_kind_that_is_not_usage_or_cases_is_refused(self):
        for value in (None, "", "Usage", "usage ", "usage; touch canary", "$(touch canary)", "both"):
            self.refused({"PUBLISH_KIND": value})
        self.assertIn("PUBLISH_KIND", self.refused({"PUBLISH_KIND": "nope"}).lines[0])

    def test_an_app_name_that_is_not_the_name_of_a_function_app_is_refused(self):
        for value in (None, "", "a", "-" + APP, APP + "-", "func app", f"{APP}; touch canary", f"{APP}\n", "$(touch canary)", "x" * 61, f"{APP}.scm.azurewebsites.net", "../" + APP):
            self.refused({"PUBLISH_APP": value})
        self.assertEqual(self.run_publish({"PUBLISH_APP": "ab"}, kind="cases").done.returncode, 3, "two characters are a name; this one is not in the stand-in's DNS, which is another matter")

    def test_a_group_a_subscription_a_client_and_a_tenant_that_are_not_what_they_are_called_are_refused(self):
        for name, bad in (("PUBLISH_RESOURCE_GROUP", ("", "rg of the project", "rg;touch canary", "x" * 91, "$(touch canary)")),
                          ("PUBLISH_SUBSCRIPTION", ("", "sub", "22222222-3333-4444-5555-66666666666", f"{SUBSCRIPTION} --x", f"{SUBSCRIPTION}\n", "$(touch canary)")),
                          ("PUBLISH_CLIENT_ID", ("", "client", f"x{DEPLOY_CLIENT}", f"{DEPLOY_CLIENT}; touch canary")),
                          ("PUBLISH_TENANT_ID", ("", "tenant", f"{DEPLOY_TENANT}0", "$(touch canary)"))):
            for value in (None, *bad):
                self.refused({name: value})
            self.assertIn(name, self.refused({name: "not valid"}).lines[0])

    def test_a_token_that_is_missing_or_is_not_made_of_the_characters_of_a_token_is_refused_without_being_printed_back(self):
        for value in (None, "", "short", "a token with spaces in it, longer than twenty", "x" * 19, "x" * 8001, f"{FEDERATED_TOKEN}; touch canary", f"{FEDERATED_TOKEN}\n", "$(touch canary)-0123456789abcdef"):
            self.refused({"AZURE_FEDERATED_TOKEN": value})
        self.assertIn("AZURE_FEDERATED_TOKEN", self.refused({"AZURE_FEDERATED_TOKEN": "nope"}).lines[0])

    def test_a_size_that_is_not_a_number_and_a_hold_that_is_not_from_0_to_60_are_refused(self):
        for value in (None, "", "12a", "-1", "1e3", "1" * 10, "$(touch canary)"):
            self.refused({"PUBLISH_FILE_BYTES": value})
        for value in ("61", "100", "-1", "abc", "1.5", "$(touch canary)"):
            self.refused({"PUBLISH_HOLD_SECONDS": value})

    def test_a_volume_without_the_file_that_carries_the_code_or_without_the_build_script_is_refused(self):
        for kind, name in (("usage", "usage-source.zip"), ("cases", "cases-source.zip")):
            ran = self.refused(None, kind=kind, package=False)
            self.assertIn(f"{name} is not in the secret volume", ran.lines[0], kind)
            ran = self.refused(None, kind=kind, files={"build-function-app.sh": None})
            self.assertIn("build-function-app.sh is not in the secret volume", ran.lines[0], f"{kind}: both apps are built here, from sources")
            self.assertEqual(self.run_publish(None, kind=kind).done.returncode, 0, kind)

    # --- the token --------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_federated_token_is_on_the_command_line_of_the_one_sign_in_and_in_no_environment_and_no_line_of_the_log(self):
        for kind in ("usage", "cases"):
            ran = self.run_publish(kind=kind)
            self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
            self.assertNotIn(FEDERATED_TOKEN, ran.done.stdout + ran.done.stderr)
            holders = [call for call in ran.calls if FEDERATED_TOKEN in call]
            self.assertEqual(len(holders), 1, "the sign-in of the deploy identity, and nothing else")
            self.assertTrue(holders[0].startswith("az login --service-principal"))
            self.assertFalse([call for call in ran.calls if "SAW THE TOKEN IN ITS ENVIRONMENT" in call], "it is taken out of the environment before any program runs")

    def test_the_token_of_resource_manager_is_on_the_standard_input_of_curl_and_nowhere_else(self):
        ran = self.run_publish(kind="cases")
        self.assertNotIn(ARM_TOKEN, ran.done.stdout + ran.done.stderr)
        self.assertEqual([call for call in ran.calls if ARM_TOKEN in call], [f'curl-stdin header = "Authorization: Bearer {ARM_TOKEN}"'])

    def test_what_a_failed_command_said_is_printed_in_a_few_lines_with_every_token_hidden(self):
        said = f"the assertion {FEDERATED_TOKEN} and the token {ARM_TOKEN} and a bearer {A_JWT} and Bearer {ARM_TOKEN}"
        ran = self.run_publish({"FAKE_AZ_LOGIN": "fail", "FAKE_TOKEN_IN_ERROR": said})
        self.assertEqual(ran.done.returncode, 3)
        self.assertRegex(ran.lines[-2], r"^FAIL: az login as the deploy identity: ERROR: AADSTS70021: the assertion the assertion <token> and the token", "the tokens that the message repeats are taken out of it")
        for secret in (FEDERATED_TOKEN, ARM_TOKEN, A_JWT, A_JWT.split(".")[1]):
            self.assertNotIn(secret, ran.done.stdout + ran.done.stderr)
        self.assertNotIn("second line that must not show", ran.done.stdout, "the first line of what the sign-in said, and no more")
        ran = self.run_publish({"FAKE_AZ_DEPLOY": "fail", "FAKE_TOKEN_IN_ERROR": said})
        quoted = [line for line in ran.lines if line.startswith("  ")]
        self.assertEqual(len(quoted), 3 * 8, "at most eight lines of what each of the three attempts said")
        for secret in (FEDERATED_TOKEN, ARM_TOKEN, A_JWT, A_JWT.split(".")[1]):
            self.assertNotIn(secret, ran.done.stdout + ran.done.stderr)
        self.assertTrue([line for line in ran.lines if line.startswith("  ERROR: Zip deployment failed. Deployment was successful but Reset all workers endpoint responded with Name or service not known the assertion <token>")],
                        "the tokens that the message repeats are taken out of it")
        ran = self.run_publish({"FAKE_CURL_CODES": "500", "FAKE_TOKEN_IN_ERROR": said}, kind="cases")
        for secret in (FEDERATED_TOKEN, ARM_TOKEN, A_JWT, A_JWT.split(".")[1]):
            self.assertNotIn(secret, ran.done.stdout + ran.done.stderr)

    # --- the sign-in, the size and the names ------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_package_that_arrived_short_is_never_published_and_nothing_is_called(self):
        for kind in ("usage", "cases"):
            ran = self.run_publish(kind=kind, sent=99999)
            self.assertEqual(ran.done.returncode, 3)
            self.assertRegex(ran.lines[1], r"^FAIL: (usage|cases)-source\.zip is \d+ bytes, 99999 were sent$")
            self.assertEqual(ran.lines[-1], "publish-done: exit code 3")
            self.assertEqual(ran.calls, [], "not even a sign-in: the file is checked first")
            self.assertEqual(ran.leftover, [])

    def test_a_sign_in_that_fails_is_tried_three_times_ten_seconds_apart_and_then_stops_the_run_before_any_name_is_looked_up(self):
        ran = self.run_publish({"FAKE_AZ_LOGIN": "fail"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertEqual(len(ran.calls_of("az login")), 3)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 10", "sleep 10"], "a pause between the tries and none after the last one")
        self.assertEqual([call for call in ran.calls if not call.startswith(("az login", "sleep"))], [])
        self.assertEqual(ran.lines[-1], "publish-done: exit code 3")
        self.assertEqual(ran.leftover, [])

    def test_a_sign_in_that_works_at_the_third_try_goes_on_and_a_subscription_that_cannot_be_set_stops_the_run(self):
        ran = self.run_publish({"FAKE_AZ_LOGIN": "twice"}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("az login")), 3)
        ran = self.run_publish({"FAKE_AZ_ACCOUNT": "fail"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertIn("FAIL: az account set: ERROR: The subscription of '<id>' doesn't exist.", ran.lines)
        self.assertEqual(ran.calls_of("getent"), [], "no name is looked up, and nothing is built or published")

    def test_a_name_that_is_public_or_does_not_resolve_stops_the_run_after_three_tries_and_nothing_is_built_or_published(self):
        for dns, host, said in ((f"{APP}.scm.azurewebsites.net=20.50.1.2 {APP}.azurewebsites.net=10.53.0.21", f"{APP}.scm.azurewebsites.net", "resolves to a public address"),
                                (f"{APP}.scm.azurewebsites.net=10.53.0.21", f"{APP}.azurewebsites.net", "does not resolve")):
            ran = self.run_publish({"FAKE_DNS": dns})
            self.assertEqual(ran.done.returncode, 3, ran.lines)
            self.assertIn(f"FAIL: {host} {said}: the private endpoint's name is not registered (yet)", ran.lines)
            self.assertEqual(len([call for call in ran.calls if call.startswith("getent") and call.endswith(host)]), 3)
            self.assertEqual(ran.calls_of("sleep"), ["sleep 10", "sleep 10"])
            self.assertEqual([call for call in ran.calls if call.startswith(("python3", "curl", "az functionapp"))], [])
            self.assertEqual(ran.leftover, [])

    def test_a_name_that_the_landing_zone_registers_at_the_second_try_is_waited_for_ten_seconds(self):
        ran = self.run_publish({"FAKE_DNS": f"{APP}.azurewebsites.net=10.53.0.21", "FAKE_DNS_LATE": f"{APP}.scm.azurewebsites.net=10.53.0.21"}, kind="usage")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 10", "sleep 20"], "ten seconds for the name, and the hold at the end")
        self.assertIn(f"ok: {APP}.scm.azurewebsites.net resolves to a private address", ran.lines)

    # --- the usage app ----------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_without_a_working_ensurepip_the_usage_app_is_not_built_and_not_published(self):
        ran = self.run_publish({"FAKE_ENSUREPIP": "disabled"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertTrue([line for line in ran.lines if line.startswith("FAIL: python3 -m ensurepip: ERROR: ensurepip is disabled in this Python: install the python3-pip")], ran.lines)
        self.assertEqual([call for call in ran.calls if call.startswith(("python3 -m pip install", "az functionapp"))], [])
        self.assertEqual(ran.leftover, [])

    def test_sources_that_would_be_unpacked_outside_the_folder_are_refused(self):
        evil = source_zip({"function_app.py": b"#\n", "../escape.txt": b"x"})
        ran = self.run_publish(package=evil)
        self.assertEqual(ran.done.returncode, 3)
        self.assertIn("FAIL: the sources could not be unpacked: a file of the sources would be unpacked outside the folder", ran.lines)
        self.assertEqual([call for call in ran.calls if call.startswith(("python3 -m pip install", "az functionapp"))], [])

    def test_a_build_that_fails_is_tried_once_more_fifteen_seconds_later_and_a_second_failure_ends_the_run_without_a_publish(self):
        ran = self.run_publish({"FAKE_PIP": "hash"})
        self.assertEqual(ran.done.returncode, 3)
        failures = [line for line in ran.lines if line.startswith("FAIL: the build")]
        self.assertEqual(failures, ["FAIL: the build of the libraries failed (attempt 1 of 2)", "FAIL: the build of the libraries failed (attempt 2 of 2)"])
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 2)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 15", "sleep 20"], "one pause between the two attempts, and the hold at the end, so that the log can be read whole")
        self.assertIn("  ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE. ", ran.lines)
        self.assertEqual(ran.calls_of("az functionapp"), [])
        self.assertEqual(ran.leftover, [])

    def test_a_build_that_fails_once_and_then_works_goes_on_to_the_publish(self):
        ran = self.run_publish({"FAKE_PIP": "first-fails"})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 2)
        self.assertIn("FAIL: the build of the libraries failed (attempt 1 of 2)", ran.lines)
        self.assertIn("  ERROR: Connection broken by 'ReadTimeoutError'", ran.lines)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 15", "sleep 20"])
        self.assertEqual(len(ran.calls_of("az functionapp")), 1)

    def test_a_compiled_module_of_another_python_than_3_13_fails_the_build_and_says_which(self):
        ran = self.run_publish({"FAKE_PIP": "foreign"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertIn("  error: compiled modules for another Python than 3.13, the runtime of the function app: _cffi_backend.cpython-312-x86_64-linux-gnu.so", ran.lines)
        self.assertEqual(ran.calls_of("az functionapp"), [])

    def test_a_publish_that_fails_twice_is_tried_a_third_time_sixty_seconds_apart_and_each_failure_says_what_azure_said(self):
        ran = self.run_publish({"FAKE_AZ_DEPLOY": "twice"})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("az functionapp deployment")), 3)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 60", "sleep 60", "sleep 20"])
        self.assertEqual([line for line in ran.lines if "publish" in line and not line.startswith("  ")],
                         ["FAIL: the publish did not go through (attempt 1 of 3)", "FAIL: the publish did not go through (attempt 2 of 3)", f"ok: the usage package is published to {APP} (attempt 3 of 3)",
                          "publish-done: exit code 0"])
        self.assertIn("  ERROR: Zip deployment failed. Deployment was successful but Reset all workers endpoint responded with Name or service not known ", ran.lines)

    def test_a_publish_that_never_goes_through_ends_with_exit_code_1_after_three_attempts_and_the_container_still_stays_for_the_log(self):
        ran = self.run_publish({"FAKE_AZ_DEPLOY": "fail"})
        self.assertEqual(ran.done.returncode, 1)
        self.assertEqual(len(ran.calls_of("az functionapp deployment")), 3)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 60", "sleep 60", "sleep 20"], "no pause after the last attempt, and the hold at the end")
        self.assertEqual(ran.lines[-2:], [f"FAIL: the code could not be published to {APP}", "publish-done: exit code 1"])
        self.assertEqual(ran.leftover, [])

    # --- the cases app ----------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_token_of_resource_manager_that_cannot_be_had_or_is_no_token_stops_the_run_at_once_before_the_names_the_build_and_curl(self):
        for mode in ("fail", "odd"):
            ran = self.run_publish({"FAKE_AZ_TOKEN": mode}, kind="cases")
            self.assertEqual(ran.done.returncode, 3, mode)
            self.assertTrue([line for line in ran.lines if line.startswith("FAIL: az account get-access-token")], mode)
            self.assertEqual((ran.calls_of("curl"), ran.calls_of("getent"), ran.calls_of("python3 -m")), ([], [], []), f"{mode}: nothing is looked up, built or posted")
            self.assertEqual(ran.leftover, [])

    def test_the_token_of_resource_manager_is_fetched_right_after_the_sign_in_while_the_assertion_is_fresh_before_the_names_and_the_build(self):
        ran = self.run_publish(kind="cases")
        calls = [re.sub(r" \[config=.+\]$", "", call) for call in ran.calls if call.startswith(("az ", "getent", "python3 -m", "curl "))]
        self.assertTrue(calls[0].startswith("az login --service-principal"))
        self.assertEqual(calls[1], f"az account set --subscription {SUBSCRIPTION}")
        self.assertEqual(calls[2], "az account get-access-token --resource https://management.azure.com --query accessToken --output tsv")
        self.assertLess(max(i for i, call in enumerate(calls) if call.startswith("getent")), min(i for i, call in enumerate(calls) if call.startswith("python3 -m")), "the names come before the build")
        self.assertLess(max(i for i, call in enumerate(calls) if call.startswith("python3 -m pip install")), min(i for i, call in enumerate(calls) if call.startswith("curl ")), "the package is built before it is posted")

    def test_the_cases_app_is_built_like_the_usage_app_and_nothing_is_posted_when_the_build_does_not_work(self):
        for env, package, said in (({"FAKE_ENSUREPIP": "disabled"}, None, "FAIL: python3 -m ensurepip: ERROR: ensurepip is disabled"),
                                   ({"FAKE_PIP": "hash"}, None, "FAIL: the build of the libraries failed (attempt 2 of 2)"),
                                   ({"FAKE_PIP": "network"}, None, "FAIL: the build of the libraries failed (attempt 2 of 2)"),
                                   ({"FAKE_PIP": "foreign"}, None, "FAIL: the build of the libraries failed (attempt 2 of 2)"),
                                   (None, source_zip({"function_app.py": b"#\n", "../escape.txt": b"x"}), "FAIL: the sources could not be unpacked: a file of the sources would be unpacked outside the folder")):
            ran = self.run_publish(env, kind="cases", package=package)
            self.assertEqual(ran.done.returncode, 3, (env, ran.lines))
            self.assertTrue([line for line in ran.lines if line.startswith(said)], (said, ran.lines))
            self.assertEqual(ran.calls_of("curl"), [], "nothing is posted that was not built")
            self.assertEqual(ran.leftover, [])
        ran = self.run_publish({"FAKE_PIP": "first-fails"}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 2, "a build that fails once is tried once more, as for the usage app")
        self.assertIn("FAIL: the build of the libraries failed (attempt 1 of 2)", ran.lines)
        self.assertEqual(len(ran.calls_of("curl ")), 1)

    def test_a_site_that_answers_with_a_failure_is_tried_again_sixty_seconds_later_and_what_it_said_is_shown(self):
        ran = self.run_publish({"FAKE_CURL_CODES": "503 202"}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(ran.lines[-4:], ["FAIL: the publish was answered with HTTP 503 (attempt 1 of 5)", "  the site said nothing with HTTP 503",
                                         "ok: the deployment site took the package (HTTP 202, attempt 2 of 5)", "publish-done: exit code 0"])
        self.assertEqual(ran.calls_of("sleep"), ["sleep 60", "sleep 20"])
        self.assertEqual(len(ran.calls_of("curl ")), 2)

    def test_a_site_that_never_takes_the_package_ends_with_exit_code_1_after_five_attempts(self):
        ran = self.run_publish({"FAKE_CURL_CODES": "500", "FAKE_CURL_EXIT": "7"}, kind="cases")
        self.assertEqual(ran.done.returncode, 1)
        self.assertEqual(len(ran.calls_of("curl ")), 5)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 60"] * 4 + ["sleep 20"], "four pauses and none after the last attempt, then the hold")
        self.assertEqual(ran.lines[-2:], [f"FAIL: the code could not be published to {CASES_APP}", "publish-done: exit code 1"])

    def test_only_200_and_202_are_a_published_package(self):
        for code in ("200", "202"):
            self.assertEqual(self.run_publish({"FAKE_CURL_CODES": code}, kind="cases").done.returncode, 0, code)
        for code in ("201", "000"):
            self.assertEqual(self.run_publish({"FAKE_CURL_CODES": code}, kind="cases").done.returncode, 1, code)

    # --- the hold, the shape of the log and what the script is made of ----------------------------------------------------------------------------------------------------------------

    def test_the_container_stays_as_long_as_it_is_asked_after_the_work_and_not_at_all_at_zero_and_a_refusal_does_not_wait(self):
        ran = self.run_publish({"PUBLISH_HOLD_SECONDS": "7"}, kind="cases")
        self.assertEqual(ran.calls[-1], "sleep 7", "the hold comes after the work")
        self.assertLess(max(i for i, call in enumerate(ran.calls) if call.startswith("curl ")), len(ran.calls) - 1)
        ran = self.run_publish({"PUBLISH_HOLD_SECONDS": "0"}, kind="cases")
        self.assertEqual(ran.calls_of("sleep"), [])
        self.assertEqual(ran.lines[-1], "publish-done: exit code 0")
        self.assertIn("sleep 60", self.run_publish({"PUBLISH_HOLD_SECONDS": "60"}, kind="cases").calls)

    def test_every_line_is_short_and_is_an_ok_a_fail_a_quoted_line_of_what_a_command_said_or_the_last_one(self):
        ran = self.run_publish({"FAKE_AZ_DEPLOY": "fail", "FAKE_TOKEN_IN_ERROR": "x" * 400})
        for line in ran.lines[:-1]:
            self.assertRegex(line, r"^(ok: |FAIL: |  )", line)
            self.assertLessEqual(len(line), 170, line)
        self.assertRegex(ran.lines[-1], r"^publish-done: exit code \d$")
        self.assertLess(len(ran.done.stdout.encode("utf-8")), 12 * 1024, "far below the 16 KB that the log of a stopped container keeps")

    def test_the_script_reads_only_the_variables_it_names_and_the_names_of_its_tests(self):
        source = text("operator/publish.sh")
        used = set(re.findall(r"\$\{?(AZURE_FEDERATED_\w+|PUBLISH_\w+|FUNCTION_APP_\w+|FAKE_\w+|GITHUB_\w+|OPERATOR_\w+)", source))
        self.assertEqual(used, {"AZURE_FEDERATED_TOKEN", "PUBLISH_KIND", "PUBLISH_APP", "PUBLISH_RESOURCE_GROUP", "PUBLISH_SUBSCRIPTION", "PUBLISH_CLIENT_ID", "PUBLISH_TENANT_ID", "PUBLISH_FILE_BYTES",
                                "PUBLISH_HOLD_SECONDS", "PUBLISH_VOLUME", "PUBLISH_TMP"})
        self.assertEqual(set(re.findall(r"\b(FUNCTION_APP_[A-Z_]+)=", re.sub(r"(?m)^\s*#.*$", "", source))), {"FUNCTION_APP_SOURCE_DIR", "FUNCTION_APP_BUILD_IN_OPERATOR"},
                         "the two switches that the build script has for the Operator, and not the third")

    def test_the_script_has_no_awk_jq_grep_find_zip_or_unzip_because_the_image_has_none_of_them_to_rely_on(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        for word in (r"\bawk\b", r"\bjq\b", r"\bgawk\b", r"\bfind\b", r"\bunzip\b", r"(?<![\w.-])zip -", r"\bgrep\b", r"\bnslookup\b", r"\bdig\b", r"\bset -x\b", r"\beval\b", r"(?m)^\s*(source|\.)\s"):
            self.assertIsNone(re.search(word, source), word)

    def test_the_script_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "publish.sh"
            script.write_text(text("operator/publish.sh"), encoding="utf-8", newline="\n")
            done = subprocess.run([BASH, "-n", posix(script)], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_the_commands_are_the_ones_that_the_runner_ran_with_the_same_flags_and_attempts(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        self.assertIn('az functionapp deployment source config-zip --resource-group "$group" --name "$app" --src "$package_zip" --build-remote false --only-show-errors --output none', source)
        self.assertIn("for attempt in 1 2 3; do\n    if message=$(timeout 600 az functionapp deployment source config-zip", source, "three attempts")
        self.assertIn("sleep 60", source, "a minute between two attempts")
        for flag in ("--silent", "--show-error", "--write-out '%{http_code}'", "--max-time 900", "--request POST", "--header 'Content-Type: application/zip'", '--data-binary "@$package_zip"',
                     'https://$app.scm.azurewebsites.net/api/zipdeploy', "--resource https://management.azure.com"):
            self.assertIn(flag, source, flag)
        self.assertIn("for attempt in 1 2 3 4 5; do", source, "five attempts, as on the runner")
        self.assertIn('if [ "$code" = 200 ] || [ "$code" = 202 ]; then', source)
        workflow = text(".github/workflows/deploy-hub.yml")
        self.assertFalse("config-zip" in workflow, "the runner does not publish any more: this script is the one way")
        self.assertFalse("/api/zipdeploy" in workflow, "the runner does not post a package any more either")


def members_of(zip_path):
    """The files of a zip, by name: Info-ZIP, which the runner has, also stores an entry for each folder, and Python's zipfile, which the container uses, does not."""
    with zipfile.ZipFile(zip_path) as archive:
        return sorted(name for name in archive.namelist() if not name.endswith("/"))


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheBuildScriptInTheOperator(unittest.TestCase):
    """tools/build-function-app.sh in its three modes against a stand-in for pip (the real Python does the rest): the sources that go to the Operator, the build there with the switches for the Operator,
    and the build on the runner; the pip command is one and the layout is one."""

    def run_build(self, arguments=("usage-functions", "usage"), env=None, python="3.13.0", source=None, zip_name="out.zip", prior=None):
        """Runs the script in a folder of its own. Returns the process, the calls that the stand-in logged, the members of the zip (or None), and the names that the build folder holds."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            (bin_dir / "python3").write_text(STUB_PYTHON, encoding="utf-8", newline="\n")
            (bin_dir / "python3").chmod(0o755)
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            build = tmp / "build"
            zip_file = tmp / zip_name
            command = [BASH, "-e", "-o", "pipefail", posix(ROOT / "tools" / "build-function-app.sh"), *arguments, posix(build), posix(zip_file)]
            environment = {**os.environ, "PATH": f"{posix(bin_dir)}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": posix(log), "FAKE_PYTHON_VERSION": python, "REAL_PYTHON": posix(sys.executable),
                           **({"FUNCTION_APP_SOURCE_DIR": posix(source)} if source else {}), **(env or {})}
            if prior is not None:
                tmp_source = prior(tmp)
                environment["FUNCTION_APP_SOURCE_DIR"] = posix(tmp_source)
            done = subprocess.run(command, capture_output=True, text=True, env=environment, cwd=ROOT)
            calls = log.read_text(encoding="utf-8").splitlines()
            members = members_of(zip_file) if zip_file.exists() else None
            self.last_zip = zip_file.read_bytes() if zip_file.exists() else None
            return done, calls, members, sorted(path.name for path in build.iterdir()) if build.exists() else []

    APPS = {"usage": ("usage-functions", "usage"), "cases": ("case-functions", "cases")}
    EXPECTED_LIBRARIES = [".python_packages/lib/site-packages/azure/core/__init__.py", ".python_packages/lib/site-packages/cffi/_rust.abi3.so",
                          ".python_packages/lib/site-packages/markupsafe/_speedups.cpython-313-x86_64-linux-gnu.so"]

    @staticmethod
    def expected_sources(kind):
        """What the build copies of an app: its three files and everything of its code package, except the compiled caches (the tests are in a folder next to the package and are not copied)."""
        directory, package = TheBuildScriptInTheOperator.APPS[kind]
        root = ROOT / "src" / directory
        code = [f"{package}/{path.relative_to(root / package).as_posix()}" for path in sorted((root / package).rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
        return sorted(["function_app.py", "host.json", "requirements.txt"] + code)

    def test_the_sources_of_each_app_are_zipped_without_libraries_whatever_python_runs_the_script(self):
        for kind, arguments in self.APPS.items():
            done, calls, members, folder = self.run_build(arguments=arguments, env={"FUNCTION_APP_SOURCES_ONLY": "1"}, python="3.12.7")
            self.assertEqual(done.returncode, 0, (kind, done.stderr))
            self.assertEqual(members, self.expected_sources(kind), f"{kind}: what the build copies, and nothing of the tests, the caches or the libraries")
            self.assertEqual([call for call in calls if call.startswith("python3 -m pip")], [], "nothing is installed")
            self.assertEqual(folder, sorted({name.split("/")[0] for name in self.expected_sources(kind)}))
            sent = len(self.last_zip) + (ROOT / "tools" / "build-function-app.sh").stat().st_size + (ROOT / "operator" / "publish.sh").stat().st_size
            self.assertLess(sent, 480_000, f"{kind}: the files of the group (the sources, the build script and the container script) are within the cap of tools/operator-run.py: "
                                           "the libraries are made in the container")
        self.assertTrue([name for name in self.expected_sources("cases") if name.startswith("cases/web/")], "the cases package has a sub-package, and the build copies it")

    def test_the_sources_are_zipped_only_when_a_zip_file_is_named_and_the_two_switches_are_not_set_together_or_set_to_anything_but_1(self):
        for env, said in (({"FUNCTION_APP_SOURCES_ONLY": "1", "FUNCTION_APP_BUILD_IN_OPERATOR": "1"}, "are not set together"), ({"FUNCTION_APP_SOURCES_ONLY": "yes"}, "are 1 or not set"),
                          ({"FUNCTION_APP_BUILD_IN_OPERATOR": "true"}, "are 1 or not set")):
            done, calls, members, folder = self.run_build(env=env)
            self.assertEqual(done.returncode, 1, env)
            self.assertIn(said, done.stderr)
            self.assertEqual((calls, folder), ([], []), "nothing is copied and nothing is installed")
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([BASH, "-e", "-o", "pipefail", posix(ROOT / "tools" / "build-function-app.sh"), "usage-functions", "usage", posix(Path(tmp) / "b")], capture_output=True, text=True,
                                  env={**os.environ, "FUNCTION_APP_SOURCES_ONLY": "1"}, cwd=ROOT)
        self.assertEqual(done.returncode, 1)
        self.assertIn("the fourth argument is the zip file", done.stderr)

    def test_the_build_in_the_operator_runs_under_python_3_12_and_makes_the_zip_with_python_and_says_how_many_files(self):
        for kind, arguments in self.APPS.items():
            done, calls, members, folder = self.run_build(arguments=arguments, env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "ok"}, python="3.12.7")
            self.assertEqual(done.returncode, 0, (kind, done.stderr))
            self.assertEqual(members, sorted(self.expected_sources(kind) + self.EXPECTED_LIBRARIES))
            self.assertEqual(done.stdout.strip(), f"{len(members)} files", "the summary is Python's: the image has no unzip")
            self.assertTrue([call for call in calls if call.startswith("python3 -m pip install")])

    def test_the_guard_of_the_runner_is_still_there_without_the_switch_and_pip_has_to_run_with_it(self):
        done, calls, members, folder = self.run_build(python="3.12.7")
        self.assertEqual(done.returncode, 1)
        self.assertIn("build with Python 3.13", done.stderr)
        self.assertEqual((calls, folder), ([], []), "nothing is downloaded and nothing is copied before the refusal")
        done, calls, members, folder = self.run_build(env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "missing"}, python="3.12.7")
        self.assertEqual(done.returncode, 1)
        self.assertIn("pip does not run in this Python", done.stderr)
        self.assertEqual(folder, [], "nothing is copied when there is no pip")

    def test_a_lock_without_hashes_is_refused_in_the_operator_before_pip_is_asked(self):
        def sources(tmp):
            folder = tmp / "sources"
            for name in ("function_app.py", "host.json", "requirements.txt"):
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(b"azure-core==1.41.0\n" if name == "requirements.txt" else b"x\n")
            (folder / "usage").mkdir()
            (folder / "usage" / "__init__.py").write_bytes(b"")
            return folder
        done, calls, members, folder = self.run_build(env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "ok"}, python="3.12.7", prior=sources)
        self.assertEqual(done.returncode, 1)
        self.assertIn("carries no hashes", done.stderr)
        self.assertEqual([call for call in calls if "pip install" in call], [])

    def test_a_compiled_module_for_another_python_than_3_13_fails_the_build_in_the_operator(self):
        done, calls, members, folder = self.run_build(env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "foreign"}, python="3.12.7")
        self.assertEqual(done.returncode, 1)
        self.assertIn("compiled modules for another Python than 3.13", done.stderr)
        self.assertIn("_cffi_backend.cpython-312-x86_64-linux-gnu.so", done.stderr)
        self.assertIsNone(members, "no zip is made of a package that would not load")

    def test_the_build_on_the_runner_and_the_build_in_the_operator_use_the_same_pip_command_and_make_the_same_package_for_each_app(self):
        def words_of(calls):
            (install,) = [call for call in calls if call.startswith("python3 -m pip install")]
            words = install.split(" [PYTHONPATH")[0].split()
            return [word for index, word in enumerate(words) if word not in ("--target", "--requirement") and words[index - 1] not in ("--target", "--requirement")]

        all_words = {}
        for kind, arguments in self.APPS.items():
            runner, runner_calls, runner_members, _ = self.run_build(arguments=arguments, env={"FAKE_PIP": "ok"}, python="3.13.0")
            self.assertEqual(runner.returncode, 0, (kind, runner.stderr))
            done, _, sources_members, _ = self.run_build(arguments=arguments, env={"FUNCTION_APP_SOURCES_ONLY": "1"}, python="3.13.0", zip_name="sources.zip")
            self.assertEqual(done.returncode, 0, (kind, done.stderr))
            sources_zip = self.last_zip

            def unpacked(tmp, sources_zip=sources_zip):
                (tmp / "sources.zip").write_bytes(sources_zip)
                with zipfile.ZipFile(tmp / "sources.zip") as archive:
                    archive.extractall(tmp / "unpacked")
                return tmp / "unpacked"

            operator, operator_calls, operator_members, _ = self.run_build(arguments=arguments, env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "ok"}, python="3.12.7", prior=unpacked)
            self.assertEqual(operator.returncode, 0, (kind, operator.stderr))
            self.assertEqual(operator_members, runner_members, f"{kind}: the same files in the same places: the sources that went to the Operator are what the runner's build copies, and the libraries are "
                                                               "made in the same folder")
            self.assertEqual(sorted(sources_members + self.EXPECTED_LIBRARIES), runner_members)
            self.assertEqual(words_of(operator_calls), words_of(runner_calls), f"{kind}: one pip command: every flag, in the same order")
            all_words[kind] = words_of(operator_calls)
            for flag in ("--only-binary=:all:", "--require-hashes", "--no-compile", "--platform", "--implementation", "--python-version"):
                self.assertIn(flag, all_words[kind])
            self.assertIn("3.13", all_words[kind])
            self.assertNotIn("--ignore-requires-python", all_words[kind])
        self.assertEqual(all_words["usage"], all_words["cases"], "the same command for both apps")

    @staticmethod
    def parse_lock(path):
        """The packages of a hash lock: name -> (version, the sorted hashes), and the lines that carry an environment marker."""
        packages, markers, current = {}, [], None
        for line in text(path).split("\n"):
            found = re.match(r"^([A-Za-z0-9_.-]+)==(\S+)", line)
            if found:
                current = found.group(1).lower()
                packages[current] = [found.group(2), []]
            for digest in re.findall(r"--hash=sha256:([0-9a-f]{64})", line):
                packages[current][1].append(digest)
            if not line.lstrip().startswith("#") and ";" in line:
                markers.append(line)
        return {name: (version, sorted(hashes)) for name, (version, hashes) in packages.items()}, markers

    def test_the_lock_of_the_cases_app_holds_only_what_the_lock_of_the_usage_app_holds_which_is_what_the_operator_has_built_under_python_3_12(self):
        # The probe of the Operator (2026-11-06) and the first publish of the usage app built the usage lock in the image's Python 3.12, with the pip command of the build script and without
        # --ignore-requires-python. Nothing built the cases lock there yet. Every package of it, at its version and with the same hashes, is in the usage lock, so it is a part of what was built.
        # If the cases app gets a library that the usage lock does not hold, this test fails: show that it builds in the Operator (an action of its own, or the first `cases` run), then change it.
        usage, usage_markers = self.parse_lock("src/usage-functions/requirements.txt")
        cases, cases_markers = self.parse_lock("src/case-functions/requirements.txt")
        self.assertEqual(sorted(cases), ["azure-functions", "markupsafe", "werkzeug"])
        for name, (version, hashes) in cases.items():
            self.assertIn(name, usage, f"{name}: a library of the cases app that the usage lock does not hold has not been built in the Operator")
            self.assertEqual(usage[name], (version, hashes), f"{name}: the same version and the same files as the lock that was built in the Operator")
        for markers in (usage_markers, cases_markers):
            self.assertEqual(markers, [], "no environment marker in a lock: pip evaluates it for the interpreter that runs it, which is 3.12 in the Operator and 3.13 on the runner")
        self.assertTrue(all(hashes for _, hashes in cases.values()), "every library of the lock is checked against hashes")
