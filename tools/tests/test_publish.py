import hashlib
import importlib.util
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


APP = CASES_APP = "func-meternaut-cases-0a1b2c3d"
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
# It is GitHub too, for the fetch of the sources: a request to api.github.com or codeload.github.com gets the status that FAKE_GITHUB_API or FAKE_GITHUB_CODELOAD gives that host for that call in turn (200, 000 for
# no answer at all, or a failure status), and 200 gives the file FAKE_GITHUB_ARCHIVE to the file that --output names. A call that finds the token of the run in its environment says so.
{ echo "curl $*"; echo "curl-stdin $(cat)"; } >> "$FAKE_LOG"
if [ -n "${GITHUB_TOKEN:-}" ]; then echo "curl-env SAW THE GITHUB TOKEN IN ITS ENVIRONMENT" >> "$FAKE_LOG"; fi
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
case "${!#}" in
  https://api.github.com/* | https://codeload.github.com/*)
    host=${!#}
    host=${host#https://}
    host=${host%%/*}
    variable=FAKE_GITHUB_API
    if [ "$host" = codeload.github.com ]; then variable=FAKE_GITHUB_CODELOAD; fi
    codes=(${!variable:-200})
    number=$(grep -c "^curl .*https://$host/" "$FAKE_LOG")
    code=${codes[$((number - 1))]:-${codes[$((${#codes[@]} - 1))]}}
    if [ "$code" = 200 ]; then cp "$FAKE_GITHUB_ARCHIVE" "$output"; printf '200'; exit 0; fi
    printf '%s' "$code"
    if [ "$code" = 000 ]; then echo "curl: (6) Could not resolve host: $host" >&2; exit 6; fi
    echo "curl: (22) The requested URL returned error: $code" >&2
    exit 22 ;;
esac
codes=(${FAKE_CURL_CODES:-200})
number=$(grep -c '^curl .*zipdeploy' "$FAKE_LOG")
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
# ensurepip put pip; -m pip --version is FAKE_PIP (ok, or missing: no pip unless PYTHONPATH names the one that ensurepip made); -m
# ensurepip is FAKE_ENSUREPIP (ok or disabled); -m pip install is a fake download that FAKE_PIP says how it ends (ok, foreign: it unpacks a compiled module of another Python, hash, network,
# first-fails: the first attempt fails and the next works). Every other call is the real Python (REAL_PYTHON), with the paths that it is given turned into the paths that it understands.
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

CASES_SOURCE_FILES = {"function_app.py": b"# the cases app\n", "host.json": b"{}\n", "requirements.txt": b"azure-functions==2.3.0 \\\n    --hash=sha256:" + b"cd" * 32 + b"\n",
                      "cases/__init__.py": b"", "cases/loop.py": b"# loop\n", "cases/web/__init__.py": b"", "cases/web/home.py": b"# home\n"}


FIXED_TIME = (2026, 11, 9, 12, 0, 0)  # an archive holds the time of each file: fixed, so that two calls of the helper below make the same bytes


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE_DIGEST = load_module("source_digest_of_the_publish_tests", ROOT / "tools" / "source-digest.py")
RELEASE = load_module("release_of_the_publish_tests", ROOT / "src" / "case-functions" / "cases" / "release.py")
THE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
THE_REPOSITORY = "some-owner/some-repo"
THE_TOP = "some-owner-some-repo-0123456"
THE_TOKEN_OF_THE_RUN = "fake-github-token-of-the-run-4kP8sD2mQ7zX"
# What a repository holds besides the app, and what the app holds besides the code that runs: none of it is taken from the archive
THE_REST_OF_THE_REPOSITORY = {"README.md": b"# a repository\n", "tools/build-function-app.sh": b"# a tool\n", "src/case-functions/tests/test_loop.py": b"# a test\n", "src/case-functions/.funcignore": b"tests\n",
                              "src/case-functions/requirements.in": b"azure-functions\n", "docs/notes.md": b"notes\n"}


def github_zip(files=None, rest=None, also=None, stored=None):
    """The archive that GitHub makes of a commit (git archive, as a zip): one folder that holds the repository's files, the app in src/case-functions, an entry for each folder, every file deflated. `also` is
    raw entries by their whole name, for the archives that a person who wants to hurt would make, and `stored` the same without compression (an archive that is too big)."""
    entries = {f"{THE_TOP}/src/case-functions/{name}": content for name, content in (CASES_SOURCE_FILES if files is None else files).items()}
    entries.update({f"{THE_TOP}/{name}": content for name, content in (THE_REST_OF_THE_REPOSITORY if rest is None else rest).items()})
    folders = {f"{THE_TOP}/"} | {"/".join(name.split("/")[:depth]) + "/" for name in entries for depth in range(2, name.count("/") + 1)}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in sorted(folders):
            info = zipfile.ZipInfo(folder, FIXED_TIME)
            info.external_attr = 0o40755 << 16
            archive.writestr(info, b"")
        for name, content in sorted({**entries, **(also or {})}.items()):
            archive.writestr(zipfile.ZipInfo(name, FIXED_TIME), content, zipfile.ZIP_DEFLATED)
        for name, content in (stored or {}).items():
            archive.writestr(zipfile.ZipInfo(name, FIXED_TIME), content, zipfile.ZIP_STORED)
    return out.getvalue()


def held_digest(files):
    """What the workflow works out over its own checkout: the digest of the files as they are held (tools/source-digest.py)."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / name).write_bytes(content)
        return SOURCE_DIGEST.digest(Path(tmp))


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

    def good_env(self, kind="flex"):
        """Everything that the script is given on the real estate, with stand-ins that answer well. The kind is the plan that the cases app runs on: "flex" (Flex Consumption: the package is published with
        config-zip) or "cases" (a Basic plan, which is the plan when none is given: the package is posted to the deployment site). The image has no pip (FAKE_PIP=missing), and both names of the app are private."""
        env = {"PUBLISH_KIND": "cases", "PUBLISH_APP": CASES_APP, "PUBLISH_RESOURCE_GROUP": GROUP, "PUBLISH_SUBSCRIPTION": SUBSCRIPTION, "PUBLISH_CLIENT_ID": DEPLOY_CLIENT,
               "PUBLISH_TENANT_ID": DEPLOY_TENANT, "AZURE_FEDERATED_TOKEN": FEDERATED_TOKEN, "FAKE_ARM_TOKEN": ARM_TOKEN, "FAKE_PIP": "missing",
               "FAKE_DNS": " ".join(f"{CASES_APP}{suffix}=10.53.0.21" for suffix in (".scm.azurewebsites.net", ".azurewebsites.net"))}
        if kind == "flex":
            env["PUBLISH_PLAN"] = "Flex"
        return env

    def run_publish(self, env=None, kind="flex", files=None, stubs=None, archive=None, statuses=None, token=None, digest=None):
        """Runs the script as the Hub starts it: the volume holds the build script, the digest tool, the lock and the host file, and the three variables name the commit, the repository and the digest of the
        app's files in it. `files` replaces files of the volume (None removes one), `archive` is what the stand-in of curl serves as GitHub's archive of the commit (the files of CASES_SOURCE_FILES by default),
        `statuses` the statuses that it gives the two hosts in turn ({"api": "503 000", "codeload": "200"}), `token` the token of the run (a private repository) and `digest` the one that the workflow made."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in {"az": STUB_AZ, "getent": STUB_GETENT, "curl": STUB_CURL, "timeout": STUB_TIMEOUT, "sleep": STUB_SLEEP, "python3": STUB_PYTHON, **(stubs or {})}.items():
                (bin_dir / name).write_text(body, encoding="utf-8", newline="\n")
                (bin_dir / name).chmod(0o755)  # on Linux a file that is not executable is skipped in the search of the path, and the real program would answer
            volume = tmp / "op"
            volume.mkdir()
            (volume / "build-function-app.sh").write_text(text("tools/build-function-app.sh"), encoding="utf-8", newline="\n")
            for name, body in {"source-digest.py": (ROOT / "tools" / "source-digest.py").read_bytes(), "requirements.txt": CASES_SOURCE_FILES["requirements.txt"], "host.json": CASES_SOURCE_FILES["host.json"],
                               **(files or {})}.items():
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
            (tmp / "github.zip").write_bytes(github_zip() if archive is None else archive)
            served = {"FAKE_GITHUB_ARCHIVE": posix(tmp / "github.zip"), "FAKE_GITHUB_API": (statuses or {}).get("api", "200"), "FAKE_GITHUB_CODELOAD": (statuses or {}).get("codeload", "200")}
            fetched = {"PUBLISH_SOURCES_COMMIT": THE_COMMIT, "PUBLISH_SOURCES_REPOSITORY": THE_REPOSITORY, "PUBLISH_SOURCES_DIGEST": held_digest(CASES_SOURCE_FILES) if digest is None else digest, "GITHUB_TOKEN": token}
            environment = {**os.environ, "STUBS": posix(bin_dir), "PUBLISH_VOLUME": posix(volume), "PUBLISH_TMP": posix(work_root), "FAKE_LOG": posix(log), "FAKE_POSTED": posix(posted),
                           "REAL_PYTHON": posix(sys.executable), **served, **fetched, **self.good_env(kind), **(env or {})}
            for name in [name for name, value in environment.items() if value is None]:
                del environment[name]
            done = subprocess.run([BASH, "-c", 'PATH="$STUBS:$PATH"; export PATH; exec bash "$0"', posix(script)], capture_output=True, text=True, env=environment, cwd=tmp)
            return Ran(done, log.read_text(encoding="utf-8").splitlines(), sorted(path.name for path in work_root.iterdir()), posix(volume), (tmp / "canary").exists(),
                       posted.read_bytes() if posted.exists() else None)

    # --- a good run ---------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_token_for_the_app_service_resource_is_fetched_right_after_the_sign_in_while_the_assertion_is_fresh_and_only_on_flex_consumption(self):
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
        self.assertIn(f"ok: the cases package is published to {APP} (attempt 1 of 3)", ran.lines, "the publish says what it needs")

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

    @staticmethod
    def posts(ran):
        """The calls of curl that post the package to the deployment site: the other curl of a run is the download of the sources."""
        return [call for call in ran.calls_of("curl ") if "zipdeploy" in call]

    def test_a_good_cases_run_signs_in_asks_for_the_token_of_resource_manager_builds_the_package_here_and_posts_the_built_package_with_the_bearer_on_standard_input(self):
        ran = self.run_publish(kind="cases")
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        self.assertEqual([re.sub(r" in \d+ s$", " in N s", re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line)) for line in ran.lines], [
            "ok: python3 3.12.7",
            f"ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: api, {len(github_zip())} bytes in N s",
            f"ok: the app's files are taken from it: {len(CASES_SOURCE_FILES) - 2} files",
            f"ok: the files match the digest of the workflow's checkout ({held_digest(CASES_SOURCE_FILES)[:12]})",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az account set",
            "ok: az account get-access-token for Azure Resource Manager",
            f"ok: {CASES_APP}.scm.azurewebsites.net resolves to a private address",
            f"ok: {CASES_APP}.azurewebsites.net resolves to a private address",
            "ok: python3 -m ensurepip makes pip 25.0.1 in the work folder",
            f"ok: the cases package is built: {len(CASES_SOURCE_FILES) + 3} files, 1.0 MB zipped, N s, hashes ok",
            f"ok: the cases package that is published has the SHA-256 {hashlib.sha256(ran.posted).hexdigest()}",
            "ok: the deployment site took the package (HTTP 200, attempt 1 of 5)",
            "publish-done: exit code 0",
        ])
        (post,) = self.posts(ran)
        self.assertRegex(post, rf"--request POST --header Content-Type: application/zip --data-binary @/.+/publish-[^/]+/cases\.zip https://{CASES_APP}\.scm\.azurewebsites\.net/api/zipdeploy")
        for flag in ("--config -", "--silent", "--show-error", "--write-out %{http_code}", "--max-time 900"):
            self.assertIn(flag, post)
        self.assertNotIn(ARM_TOKEN, post, "the bearer is on no command line")
        self.assertEqual([call for call in ran.calls_of("curl-stdin") if ARM_TOKEN in call], [f'curl-stdin header = "Authorization: Bearer {ARM_TOKEN}"'])
        self.assertEqual(ran.calls_of("curl-file"), [f"curl-file {len(ran.posted)} {hashlib.sha256(ran.posted).hexdigest()}"], "the package is posted whole, byte for byte")
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES), "the files of the app that were fetched, the lock and the host file of the request, and the libraries built here")
        self.assertEqual(ran.calls_of("az functionapp"), [], "the cases are published with curl, as the runner did")
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 1, "the package is built here, once")
        self.assertEqual(ran.leftover, [])
        self.assertEqual(ran.calls[-1], "sleep 20")

    def test_a_good_cases_run_on_flex_consumption_is_published_with_config_zip_and_the_only_curl_is_the_download_of_the_sources(self):
        ran = self.run_publish({"PUBLISH_PLAN": "Flex"}, kind="cases")
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        self.assertEqual([re.sub(r" [0-9a-f]{64}$", " HASH", re.sub(r" in \d+ s$", " in N s", re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line))) for line in ran.lines], [
            "ok: python3 3.12.7",
            f"ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: api, {len(github_zip())} bytes in N s",
            f"ok: the app's files are taken from it: {len(CASES_SOURCE_FILES) - 2} files",
            f"ok: the files match the digest of the workflow's checkout ({held_digest(CASES_SOURCE_FILES)[:12]})",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az account set",
            "ok: az token for the App Service resource, fetched while the OpenID Connect token is fresh",
            f"ok: {CASES_APP}.scm.azurewebsites.net resolves to a private address",
            f"ok: {CASES_APP}.azurewebsites.net resolves to a private address",
            "ok: az 2.92.0",
            "ok: python3 -m ensurepip makes pip 25.0.1 in the work folder",
            f"ok: the cases package is built: {len(CASES_SOURCE_FILES) + 3} files, 1.0 MB zipped, N s, hashes ok",
            "ok: the cases package that is published has the SHA-256 HASH",
            f"ok: the cases package is published to {CASES_APP} (attempt 1 of 3)",
            "publish-done: exit code 0",
        ])
        az_calls = ran.calls_of("az ")
        self.assertTrue(az_calls[0].startswith("az login --service-principal"), "the sign-in comes before any other call of az")
        self.assertRegex(az_calls[0], rf"^az login --service-principal --username {DEPLOY_CLIENT} --tenant {DEPLOY_TENANT} --federated-token {FEDERATED_TOKEN} --allow-no-subscriptions --output none "
                                      r"\[config=/.+/publish-[^/]+/azure\]$")
        self.assertRegex(ran.calls_of("az account")[0], rf"^az account set --subscription {SUBSCRIPTION} \[config=/.+/publish-[^/]+/azure\]$")
        (publish,) = ran.calls_of("az functionapp")
        self.assertRegex(publish, rf"^az functionapp deployment source config-zip --resource-group {GROUP} --name {CASES_APP} --src /.+/publish-[^/]+/cases\.zip --build-remote false --only-show-errors --output none ")
        self.assertEqual(self.posts(ran), [], "a Flex Consumption app has no zip deployment that curl posts to: it is published with the Azure CLI's zip deployment command")
        (download,) = ran.calls_of("curl ")
        self.assertIn("https://api.github.com/repos/", download, "the one curl of a Flex run is the download of the sources, before the sign-in")
        self.assertLess(ran.calls.index(download), min(i for i, call in enumerate(ran.calls) if call.startswith("az ")))
        (token,) = ran.calls_of("az account get-access-token")
        self.assertIn("--resource https://appservice.azure.com", token, "the token that config-zip asks Microsoft Entra for, fetched while the OpenID Connect token is fresh")
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES), "the files that were fetched, and the libraries that were built here")
        self.assertEqual(ran.leftover, [], "the work folder, with the CLI's state of the deploy identity and what was built, is gone")
        self.assertEqual(ran.calls[-1], "sleep 20", "the container stays after the work so that the log can be read whole")

    def test_a_cases_run_with_no_plan_is_a_basic_run_and_a_plan_that_is_not_flex_or_basic_is_refused(self):
        ran = self.run_publish({"PUBLISH_PLAN": None}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(self.posts(ran)), 1, "no plan: Basic, as it was before the plan was a setting")
        self.assertEqual(ran.calls_of("az functionapp"), [])
        ran = self.run_publish({"PUBLISH_PLAN": "Basic"}, kind="cases")
        self.assertEqual(len(self.posts(ran)), 1)
        for value in ("flex", "basic", "Basic ", " Flex", "Premium", "FlexConsumption", "Flex; touch canary", "$(touch canary)", "Flex\nBasic"):
            self.refused({"PUBLISH_PLAN": value}, kind="cases")
        self.assertIn("PUBLISH_PLAN", self.refused({"PUBLISH_PLAN": "nope"}, kind="cases").lines[0])
        ran = self.run_publish({"PUBLISH_PLAN": "Flex"})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("az functionapp")), 1)

    def test_the_package_that_az_publishes_is_the_one_that_was_built_here_from_the_files_that_were_fetched(self):
        ran = self.run_publish()
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES))

    def test_the_two_plan_kinds_are_built_by_the_same_command_with_the_same_flags_and_differ_only_in_the_way_that_the_package_is_published(self):
        installs = {}
        for kind in ("flex", "cases"):
            ran = self.run_publish(kind=kind)
            (install,) = [call for call in ran.calls if call.startswith("python3 -m pip install")]
            installs[kind] = re.sub(r"/[^ ]*/publish-[^/ ]+/", "<work>/", install)
        self.assertEqual(installs["flex"], installs["cases"], "one pip command, one layout")
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/publish.sh"))
        self.assertNotIn("usage", source, "the usage app was removed on 2026-11-07: the script publishes the cases app only")
        self.assertIn('publish_flex case-functions cases cases', source, "the web page's app on Flex Consumption is built and published with the Azure CLI's zip deployment command")
        self.assertIn('build_package case-functions cases cases || return 3', source, "and on a Basic plan it is built here too, and posted")
        self.assertEqual(source.count('timeout 300 bash "$volume/build-function-app.sh"'), 1, "the build is run in one place, for both plan kinds")
        self.assertEqual(source.count("python3 -m pip install"), 0, "and pip is run by the build script alone")

    # --- the input is refused before anything runs --------------------------------------------------------------------------------------------------------------------------------------

    def refused(self, env, kind="flex", **kwargs):
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

    def test_a_kind_that_is_not_cases_is_refused_and_the_usage_app_is_not_a_kind_any_more(self):
        for value in (None, "", "Cases", "cases ", "cases; touch canary", "$(touch canary)", "usage", "both"):
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

    def test_a_hold_that_is_not_from_0_to_60_is_refused(self):
        for value in ("61", "100", "-1", "abc", "1.5", "$(touch canary)"):
            self.refused({"PUBLISH_HOLD_SECONDS": value})

    def test_a_volume_that_lacks_a_file_of_the_request_is_refused_before_anything_runs(self):
        for kind in ("flex", "cases"):
            for name in ("build-function-app.sh", "source-digest.py", "requirements.txt", "host.json"):
                ran = self.refused(None, kind=kind, files={name: None})
                self.assertIn(f"{name} is not in the secret volume", ran.lines[0], f"{kind}: {name}")
            self.assertEqual(self.run_publish(None, kind=kind).done.returncode, 0, kind)

    # --- the token --------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_federated_token_is_on_the_command_line_of_the_one_sign_in_and_in_no_environment_and_no_line_of_the_log(self):
        for kind in ("flex", "cases"):
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

    # --- the sign-in, the names and the build -----------------------------------------------------------------------------------------------------------------------------------------

    def test_a_sign_in_that_fails_is_tried_three_times_ten_seconds_apart_and_then_stops_the_run_before_any_name_is_looked_up(self):
        ran = self.run_publish({"FAKE_AZ_LOGIN": "fail"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertEqual(len(ran.calls_of("az login")), 3)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 10", "sleep 10"], "a pause between the tries and none after the last one")
        self.assertEqual([call for call in ran.calls if not call.startswith(("az login", "sleep", "curl"))], [], "the download of the sources came first, and nothing else ran")
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
            self.assertEqual([call for call in ran.calls if call.startswith(("python3 -m", "az functionapp")) or "zipdeploy" in call], [])
            self.assertEqual(ran.leftover, [])

    def test_a_name_that_the_landing_zone_registers_at_the_second_try_is_waited_for_ten_seconds(self):
        ran = self.run_publish({"FAKE_DNS": f"{APP}.azurewebsites.net=10.53.0.21", "FAKE_DNS_LATE": f"{APP}.scm.azurewebsites.net=10.53.0.21"})
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(ran.calls_of("sleep"), ["sleep 10", "sleep 20"], "ten seconds for the name, and the hold at the end")
        self.assertIn(f"ok: {APP}.scm.azurewebsites.net resolves to a private address", ran.lines)

    # --- a Flex Consumption app: published with the Azure CLI ---------------------------------------------------------------------------------------------------------------------------

    def test_without_a_working_ensurepip_the_app_is_not_built_and_not_published(self):
        ran = self.run_publish({"FAKE_ENSUREPIP": "disabled"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertTrue([line for line in ran.lines if line.startswith("FAIL: python3 -m ensurepip: ERROR: ensurepip is disabled in this Python: install the python3-pip")], ran.lines)
        self.assertEqual([call for call in ran.calls if call.startswith(("python3 -m pip install", "az functionapp"))], [])
        self.assertEqual(ran.leftover, [])

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
        self.assertEqual([line for line in ran.lines if "publish" in line and not line.startswith("  ") and "SHA-256" not in line],
                         ["FAIL: the publish did not go through (attempt 1 of 3)", "FAIL: the publish did not go through (attempt 2 of 3)", f"ok: the cases package is published to {APP} (attempt 3 of 3)",
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
            self.assertEqual((self.posts(ran), ran.calls_of("getent"), ran.calls_of("python3 -m")), ([], [], []), f"{mode}: nothing is looked up, built or posted")
            self.assertEqual(ran.leftover, [])

    def test_the_token_of_resource_manager_is_fetched_right_after_the_sign_in_while_the_assertion_is_fresh_before_the_names_and_the_build(self):
        ran = self.run_publish(kind="cases")
        calls = [re.sub(r" \[config=.+\]$", "", call) for call in ran.calls if call.startswith(("az ", "getent", "python3 -m")) or "zipdeploy" in call]
        self.assertTrue(calls[0].startswith("az login --service-principal"))
        self.assertEqual(calls[1], f"az account set --subscription {SUBSCRIPTION}")
        self.assertEqual(calls[2], "az account get-access-token --resource https://management.azure.com --query accessToken --output tsv")
        self.assertLess(max(i for i, call in enumerate(calls) if call.startswith("getent")), min(i for i, call in enumerate(calls) if call.startswith("python3 -m")), "the names come before the build")
        self.assertLess(max(i for i, call in enumerate(calls) if call.startswith("python3 -m pip install")), min(i for i, call in enumerate(calls) if call.startswith("curl ")), "the package is built before it is posted")

    def test_the_cases_app_on_a_basic_plan_is_built_here_and_nothing_is_posted_when_the_build_does_not_work(self):
        for env, said in (({"FAKE_ENSUREPIP": "disabled"}, "FAIL: python3 -m ensurepip: ERROR: ensurepip is disabled"),
                          ({"FAKE_PIP": "hash"}, "FAIL: the build of the libraries failed (attempt 2 of 2)"),
                          ({"FAKE_PIP": "network"}, "FAIL: the build of the libraries failed (attempt 2 of 2)"),
                          ({"FAKE_PIP": "foreign"}, "FAIL: the build of the libraries failed (attempt 2 of 2)")):
            ran = self.run_publish(env, kind="cases")
            self.assertEqual(ran.done.returncode, 3, (env, ran.lines))
            self.assertTrue([line for line in ran.lines if line.startswith(said)], (said, ran.lines))
            self.assertEqual(self.posts(ran), [], "nothing is posted that was not built")
            self.assertEqual(ran.leftover, [])
        ran = self.run_publish({"FAKE_PIP": "first-fails"}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(len(ran.calls_of("python3 -m pip install")), 2, "a build that fails once is tried once more")
        self.assertIn("FAIL: the build of the libraries failed (attempt 1 of 2)", ran.lines)
        self.assertEqual(len(self.posts(ran)), 1)

    def test_a_site_that_answers_with_a_failure_is_tried_again_sixty_seconds_later_and_what_it_said_is_shown(self):
        ran = self.run_publish({"FAKE_CURL_CODES": "503 202"}, kind="cases")
        self.assertEqual(ran.done.returncode, 0, ran.done.stdout)
        self.assertEqual(ran.lines[-4:], ["FAIL: the publish was answered with HTTP 503 (attempt 1 of 5)", "  the site said nothing with HTTP 503",
                                         "ok: the deployment site took the package (HTTP 202, attempt 2 of 5)", "publish-done: exit code 0"])
        self.assertEqual(ran.calls_of("sleep"), ["sleep 60", "sleep 20"])
        self.assertEqual(len(self.posts(ran)), 2)

    def test_a_site_that_never_takes_the_package_ends_with_exit_code_1_after_five_attempts(self):
        ran = self.run_publish({"FAKE_CURL_CODES": "500", "FAKE_CURL_EXIT": "7"}, kind="cases")
        self.assertEqual(ran.done.returncode, 1)
        self.assertEqual(len(self.posts(ran)), 5)
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
        self.assertEqual(used, {"AZURE_FEDERATED_TOKEN", "PUBLISH_KIND", "PUBLISH_PLAN", "PUBLISH_APP", "PUBLISH_RESOURCE_GROUP", "PUBLISH_SUBSCRIPTION", "PUBLISH_CLIENT_ID", "PUBLISH_TENANT_ID",
                                "PUBLISH_HOLD_SECONDS", "PUBLISH_VOLUME", "PUBLISH_TMP", "PUBLISH_SOURCES_COMMIT", "PUBLISH_SOURCES_REPOSITORY", "PUBLISH_SOURCES_DIGEST", "GITHUB_TOKEN"})
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
        self.assertEqual(workflow.count("config-zip"), 0, "the runner publishes no app: every app goes through this script")
        self.assertFalse("/api/zipdeploy" in workflow, "the runner does not post a package any more either")


def members_of(zip_path):
    """The files of a zip, by name: Info-ZIP, which the runner has, also stores an entry for each folder, and Python's zipfile, which the container uses, does not."""
    with zipfile.ZipFile(zip_path) as archive:
        return sorted(name for name in archive.namelist() if not name.endswith("/"))


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheBuildScriptInTheOperator(unittest.TestCase):
    """tools/build-function-app.sh in its two modes against a stand-in for pip (the real Python does the rest): the build in the Operator with the switch for it, and the build on the runner; the pip command
    is one and the layout is one."""

    def run_build(self, arguments=("case-functions", "cases"), env=None, python="3.13.0", source=None, zip_name="out.zip", prior=None):
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

    APPS = {"cases": ("case-functions", "cases")}
    EXPECTED_LIBRARIES = [".python_packages/lib/site-packages/azure/core/__init__.py", ".python_packages/lib/site-packages/cffi/_rust.abi3.so",
                          ".python_packages/lib/site-packages/markupsafe/_speedups.cpython-313-x86_64-linux-gnu.so"]

    @staticmethod
    def expected_sources(kind):
        """What the build copies of an app: its three files and everything of its code package, except the compiled caches (the tests are in a folder next to the package and are not copied)."""
        directory, package = TheBuildScriptInTheOperator.APPS[kind]
        root = ROOT / "src" / directory
        code = [f"{package}/{path.relative_to(root / package).as_posix()}" for path in sorted((root / package).rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
        return sorted(["function_app.py", "host.json", "requirements.txt"] + code)

    def test_the_package_that_an_app_runs_from_is_deflate_in_each_build_that_makes_one_because_the_deployment_site_cannot_read_lzma(self):
        for label, env, python in (("the runner's build", {"FAKE_PIP": "ok"}, "3.13.0"), ("the build in the Operator", {"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "ok"}, "3.12.7")):
            done, calls, members, folder = self.run_build(env=env, python=python)
            self.assertEqual(done.returncode, 0, (label, done.stderr))
            with zipfile.ZipFile(io.BytesIO(self.last_zip)) as package:
                methods = {info.compress_type for info in package.infolist()}
                self.assertIn(zipfile.ZIP_DEFLATED, methods, label)
                self.assertLessEqual(methods, {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, f"{label}: only what the deployment site reads (Info-ZIP stores a file that is empty)")

    def test_the_switch_for_the_operator_is_1_or_not_set_and_anything_else_is_refused_before_anything_is_copied(self):
        for value in ("yes", "true", "0", "2"):
            done, calls, members, folder = self.run_build(env={"FUNCTION_APP_BUILD_IN_OPERATOR": value})
            self.assertEqual(done.returncode, 1, value)
            self.assertIn("FUNCTION_APP_BUILD_IN_OPERATOR is 1 or not set", done.stderr)
            self.assertEqual((calls, folder), ([], []), "nothing is copied and nothing is installed")

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
            (folder / "cases").mkdir()
            (folder / "cases" / "__init__.py").write_bytes(b"")
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

    def test_the_build_on_the_runner_and_the_build_in_the_operator_use_the_same_pip_command_and_make_the_same_package(self):
        def words_of(calls):
            (install,) = [call for call in calls if call.startswith("python3 -m pip install")]
            words = install.split(" [PYTHONPATH")[0].split()
            return [word for index, word in enumerate(words) if word not in ("--target", "--requirement") and words[index - 1] not in ("--target", "--requirement")]

        all_words = {}
        for kind, arguments in self.APPS.items():
            runner, runner_calls, runner_members, _ = self.run_build(arguments=arguments, env={"FAKE_PIP": "ok"}, python="3.13.0")
            self.assertEqual(runner.returncode, 0, (kind, runner.stderr))
            sources_members = self.expected_sources(kind)

            def copied(tmp, kind=kind, names=sources_members):
                directory = ROOT / "src" / self.APPS[kind][0]
                for name in names:
                    (tmp / "copied" / name).parent.mkdir(parents=True, exist_ok=True)
                    (tmp / "copied" / name).write_bytes((directory / name).read_bytes())
                return tmp / "copied"

            operator, operator_calls, operator_members, _ = self.run_build(arguments=arguments, env={"FUNCTION_APP_BUILD_IN_OPERATOR": "1", "FAKE_PIP": "ok"}, python="3.12.7", prior=copied)
            self.assertEqual(operator.returncode, 0, (kind, operator.stderr))
            self.assertEqual(operator_members, runner_members, f"{kind}: the same files in the same places: the files that the Operator fetched are what the runner's build copies, and the libraries are "
                                                               "made in the same folder")
            self.assertEqual(sorted(sources_members + self.EXPECTED_LIBRARIES), runner_members)
            self.assertEqual(words_of(operator_calls), words_of(runner_calls), f"{kind}: one pip command: every flag, in the same order")
            all_words[kind] = words_of(operator_calls)
            for flag in ("--only-binary=:all:", "--require-hashes", "--no-compile", "--platform", "--implementation", "--python-version"):
                self.assertIn(flag, all_words[kind])
            self.assertIn("3.13", all_words[kind])
            self.assertNotIn("--ignore-requires-python", all_words[kind])

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

    def test_the_lock_of_the_cases_app_has_three_libraries_each_with_hashes_and_no_environment_marker_which_is_what_the_operator_has_built_under_python_3_12(self):
        # The first publish of the usage app (since removed) built a lock of these libraries in the image's Python 3.12, with the pip command of the build script and without
        # --ignore-requires-python, and the probe of the Operator builds the cases lock the same way: pip evaluates an environment marker for the interpreter that runs it, which is 3.12 in the Operator and
        # 3.13 on the runner, so the lock has none.
        cases, cases_markers = self.parse_lock("src/case-functions/requirements.txt")
        self.assertEqual(sorted(cases), ["azure-functions", "markupsafe", "werkzeug"])
        self.assertEqual(cases_markers, [], "no environment marker in a lock: pip evaluates it for the interpreter that runs it, which is 3.12 in the Operator and 3.13 on the runner")
        self.assertTrue(all(hashes for _, hashes in cases.values()), "every library of the lock is checked against hashes")


class TheRequestWayIsGone(unittest.TestCase):
    """The sources reach the Operator by fetch and in no other way (docs/proposals/27-package-without-comments.md): no input of the Hub, no step of the workflow, no line of the container script, no switch of the
    build script and no tool is left of the way that squeezed them into the request. A name of it that comes back in any of them fails here."""

    REMOVED = ("cases-source", "PUBLISH_FILE_BYTES", "FUNCTION_APP_SOURCES_ONLY", "strip-sources", "lzma", "LZMA", "inputs.sources", "zip_sha256", "ZIP_SHA256",
               "steps.pack", "id: pack", "Pack the cases", "sources: request", "sources: fetch", "by request", "the request way")
    REMOVED_OF_THE_WORKFLOW = (r"sources_digest", r"(?<![A-Z_])SOURCES_DIGEST", r"(?<![A-Z_])SOURCES:", r"\$\{SOURCES\b", r"sources\.zip")

    @staticmethod
    def steps_of_the_workflow():
        return re.split(r"(?m)^      - ", text(".github/workflows/deploy-hub.yml").split("    steps:\n", 1)[1])[1:]

    def test_no_step_of_the_workflow_and_no_line_of_the_container_script_mentions_the_removed_way(self):
        steps = self.steps_of_the_workflow()
        self.assertGreater(len(steps), 50, "the workflow was read in steps")
        for step in steps:
            title = step.split("\n", 1)[0]
            for name in self.REMOVED:
                self.assertNotIn(name, step, f"the step {title!r} still mentions {name!r}")
            for pattern in self.REMOVED_OF_THE_WORKFLOW:
                self.assertIsNone(re.search(pattern, step), f"the step {title!r} still mentions {pattern!r}")
        for number, line in enumerate(text("operator/publish.sh").splitlines(), 1):
            for name in self.REMOVED:
                self.assertNotIn(name, line, f"line {number} of operator/publish.sh still mentions {name!r}")
        inputs = text(".github/workflows/deploy-hub.yml").split("    inputs:\n", 1)[1].split("\npermissions:\n", 1)[0]
        self.assertNotIn("\n      sources:", "\n" + inputs, "the Hub has no input for the way that the sources come")

    def test_the_build_script_has_no_switch_for_the_sources_and_no_lzma_and_every_zip_that_it_makes_is_deflate(self):
        script = text("tools/build-function-app.sh")
        for name in ("SOURCES_ONLY", "LZMA", "strip-sources", "sources.zip"):
            self.assertNotIn(name, script, name)
        self.assertEqual(set(re.findall(r"\bFUNCTION_APP_[A-Z_]+\b", re.sub(r"(?m)^\s*#.*$", "", script))), {"FUNCTION_APP_BUILD_IN_OPERATOR", "FUNCTION_APP_SOURCE_DIR"}, "the two switches for the Operator and nothing else")
        self.assertEqual(re.findall(r"zipfile\.ZIP_\w+", script), ["zipfile.ZIP_DEFLATED"], "the deployment site cannot read another compression")

    def test_the_tools_of_the_way_are_gone_and_the_digest_tool_loads_nothing_but_the_standard_library(self):
        for path in ("tools/strip-sources.py", "tools/tests/test_strip_sources.py"):
            self.assertFalse((ROOT / path).exists(), path)
        tool = text("tools/source-digest.py")
        for name in ("stripper", "strip-sources", "importlib"):
            self.assertNotIn(name, tool, name)
        self.assertNotIn("as_held", tool, "there is one mode, and so no parameter for it")


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheSourcesAreFetchedFromGitHub(unittest.TestCase):
    """operator/publish.sh with PUBLISH_SOURCES_COMMIT, PUBLISH_SOURCES_REPOSITORY and PUBLISH_SOURCES_DIGEST, which the Hub always sets (docs/proposals/07-private-by-default.md). The container downloads the archive
    of the commit, takes the files of the app out of it, holds their digest against the one that the workflow made over its own checkout, and stops before the sign-in when anything is wrong; the lock and the host
    file come in the request. The harness is the one of PublishScript, with a stand-in of curl that is GitHub too."""

    run_publish = PublishScript.run_publish
    good_env = PublishScript.good_env
    members_of_bytes = PublishScript.members_of_bytes
    FAKE_LIBRARIES = PublishScript.FAKE_LIBRARIES

    def fetch(self, env=None, archive=None, volume=None, kind="flex", statuses=None, token=None, digest=None):
        """A run as the Hub starts it: the three variables, and in the volume the build script, the tool that makes the digest, the lock and the host file."""
        return self.run_publish(env, kind=kind, files=volume, archive=archive, statuses=statuses, token=token, digest=digest)

    def stopped_before_the_sign_in(self, ran, said, code=3):
        fails = [line for line in ran.lines if line.startswith("FAIL: ")]
        self.assertEqual(ran.done.returncode, code, ran.lines)
        self.assertTrue([line for line in fails if said in line], (said, ran.lines))
        self.assertEqual(ran.lines[-1], f"publish-done: exit code {code}")
        self.assertEqual([call for call in ran.calls if call.startswith(("az ", "getent", "python3 -m", "curl-file")) or "zipdeploy" in call], [], "no sign-in, no name, no build and nothing published")
        self.assertIsNone(ran.posted)
        self.assertEqual(ran.leftover, [], "the work folder is gone")
        self.assertFalse(ran.canary)

    def refused(self, env, **kwargs):
        ran = self.fetch(env, **kwargs)
        self.assertEqual(ran.done.returncode, 2, (env, ran.lines))
        self.assertEqual((len(ran.lines), ran.lines[0][:6], ran.lines[1]), (2, "FAIL: ", "publish-done: exit code 2"), ran.lines)
        self.assertEqual(ran.calls, [], "nothing runs after a refusal: no download, no sign-in, no sleep")
        self.assertFalse(ran.canary)
        self.assertEqual(ran.leftover, [])
        for value in (env or {}).values():
            if value and len(value) > 8:
                self.assertNotIn(value, ran.done.stdout + ran.done.stderr, "a value is never printed back: it may be anything")
        return ran

    # --- a good run -----------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_good_fetch_takes_only_the_files_of_the_app_checks_their_digest_before_the_sign_in_and_publishes_the_package_built_from_them_as_they_are_held(self):
        archive, digest = github_zip(), held_digest(CASES_SOURCE_FILES)
        ran = self.fetch()
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        self.assertEqual([re.sub(r" [0-9a-f]{64}$", " HASH", re.sub(r" in \d+ s$", " in N s", re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line))) for line in ran.lines], [
            "ok: python3 3.12.7",
            f"ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: api, {len(archive)} bytes in N s",
            "ok: the app's files are taken from it: 5 files",
            f"ok: the files match the digest of the workflow's checkout ({digest[:12]})",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az account set",
            "ok: az token for the App Service resource, fetched while the OpenID Connect token is fresh",
            f"ok: {APP}.scm.azurewebsites.net resolves to a private address",
            f"ok: {APP}.azurewebsites.net resolves to a private address",
            "ok: az 2.92.0",
            "ok: python3 -m ensurepip makes pip 25.0.1 in the work folder",
            f"ok: the cases package is built: {len(CASES_SOURCE_FILES) + 3} files, 1.0 MB zipped, N s, hashes ok",
            "ok: the cases package that is published has the SHA-256 HASH",
            f"ok: the cases package is published to {APP} (attempt 1 of 3)",
            "publish-done: exit code 0",
        ])
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES), "the app and the libraries: nothing of the tests, the docs or the rest of the repository")
        with zipfile.ZipFile(io.BytesIO(ran.posted)) as package:
            for name, content in CASES_SOURCE_FILES.items():
                self.assertEqual(package.read(name), content, f"{name}: as the repository holds it, with its comments")
        self.assertEqual(ran.leftover, [])
        self.assertLess(max(i for i, call in enumerate(ran.calls) if call.startswith("curl ")), min(i for i, call in enumerate(ran.calls) if call.startswith("az ")), "the download comes before the sign-in")
        ran = self.fetch(kind="cases")
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        self.assertEqual([re.sub(r" in \d+ s$", " in N s", line) for line in ran.lines[:4]], ["ok: python3 3.12.7", f"ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: api, {len(archive)} bytes in N s",
                                                                                              "ok: the app's files are taken from it: 5 files", f"ok: the files match the digest of the workflow's checkout ({digest[:12]})"])
        (post,) = [call for call in ran.calls_of("curl ") if "zipdeploy" in call]
        self.assertRegex(post, rf"https://{CASES_APP}\.scm\.azurewebsites\.net/api/zipdeploy$")
        self.assertEqual(self.members_of_bytes(ran.posted), sorted(list(CASES_SOURCE_FILES) + self.FAKE_LIBRARIES))

    def test_the_real_app_is_fetched_as_it_is_held_and_the_package_has_the_digest_that_the_running_app_works_out_over_its_own_files(self):
        app = ROOT / "src" / "case-functions"
        files = {path.relative_to(app).as_posix(): path.read_bytes().replace(b"\r\n", b"\n") for path in sorted(app.rglob("*"))
                 if path.is_file() and "__pycache__" not in path.parts and path.relative_to(app).parts[0] != "tests"}
        digest = SOURCE_DIGEST.digest(app)
        ran = self.fetch(archive=github_zip(files), digest=digest, volume={"requirements.txt": files["requirements.txt"], "host.json": files["host.json"]})
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.done.stdout)
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(io.BytesIO(ran.posted)) as package:
            package.extractall(tmp)
            self.assertEqual(RELEASE.digest(Path(tmp))[0], digest, "the app works out over the files that it runs from the digest that the workflow worked out over the checkout: the control A-RELEASE passes")
            self.assertEqual(sorted(name for name in package.namelist() if not name.startswith(".python_packages/")), sorted(name for name in files if name not in (".funcignore", "requirements.in")))
            self.assertTrue([name for name in package.namelist() if name.endswith(".py") and b"\n# " in package.read(name)], "the comments of the repository are in the package: it is not stripped")

    # --- the download -----------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_archive_is_asked_for_at_the_api_with_the_flags_of_a_quiet_download_that_follows_the_redirect_and_the_token_is_on_standard_input_only(self):
        ran = self.fetch(token=THE_TOKEN_OF_THE_RUN)
        self.assertEqual(ran.done.returncode, 0, ran.lines)
        (request,) = ran.calls_of("curl ")
        self.assertRegex(request, rf"^curl --config - --fail --silent --show-error --location --max-time 30 --output /.+/publish-[^/]+/sources\.zip --write-out %\{{http_code\}} "
                                  rf"https://api\.github\.com/repos/{THE_REPOSITORY}/zipball/{THE_COMMIT}$")
        self.assertEqual(ran.calls_of("curl-stdin"), [f'curl-stdin header = "Authorization: Bearer {THE_TOKEN_OF_THE_RUN}"'], "the bearer comes on standard input")
        self.assertEqual([call for call in ran.calls if THE_TOKEN_OF_THE_RUN in call], ran.calls_of("curl-stdin"), "on no command line and in no other call")
        self.assertEqual([call for call in ran.calls if "SAW THE" in call], [], "taken out of the environment before any program runs")
        self.assertNotIn(THE_TOKEN_OF_THE_RUN, ran.done.stdout + ran.done.stderr)
        ran = self.fetch()
        self.assertEqual([call for call in ran.calls if "Authorization" in call or "Bearer" in call], [], "without a token the request is anonymous, which is enough for a public repository")

    def test_a_host_that_fails_is_tried_twice_and_then_the_other_one_and_a_refusal_that_is_not_the_token_goes_to_the_other_host_at_once(self):
        ran = self.fetch(statuses={"api": "503 000", "codeload": "200"})
        self.assertEqual(ran.done.returncode, 0, ran.lines)
        urls = [call.split()[-1] for call in ran.calls_of("curl ")]
        self.assertEqual(urls, [f"https://api.github.com/repos/{THE_REPOSITORY}/zipball/{THE_COMMIT}"] * 2 + [f"https://codeload.github.com/{THE_REPOSITORY}/zip/{THE_COMMIT}"])
        self.assertEqual(ran.calls_of("sleep")[0], "sleep 3", "a pause between the two tries at a host")
        self.assertRegex("\n".join(ran.lines), rf"(?m)^ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: codeload, \d+ bytes in \d+ s$")
        for status in ("403", "404", "429"):
            ran = self.fetch(statuses={"api": status, "codeload": "200"})
            self.assertEqual(ran.done.returncode, 0, (status, ran.lines))
            self.assertEqual(len(ran.calls_of("curl ")), 2, f"{status} is no reason to try the same host again: the anonymous limit of the API, or a commit that it does not know")
            self.assertNotIn("sleep 3", ran.calls)

    def test_a_token_that_github_refuses_stops_the_run_and_the_other_host_is_not_asked_but_the_same_status_without_a_token_goes_on(self):
        for status in ("401", "403"):
            ran = self.fetch(token=THE_TOKEN_OF_THE_RUN, statuses={"api": status})
            self.stopped_before_the_sign_in(ran, f"GitHub refused the token of this run (HTTP {status})")
            self.assertEqual(len(ran.calls_of("curl ")), 1, "one try: the other host would refuse the same token")
            self.assertNotIn(THE_TOKEN_OF_THE_RUN, ran.done.stdout + ran.done.stderr)
            ran = self.fetch(statuses={"api": status})
            self.assertEqual(ran.done.returncode, 0, f"without a token {status} is the limit of the anonymous API, and the other host answers")

    def test_a_download_that_never_works_stops_the_run_and_says_what_each_host_answered_and_what_curl_said_last(self):
        ran = self.fetch(token=THE_TOKEN_OF_THE_RUN, statuses={"api": "000", "codeload": "500"})
        self.stopped_before_the_sign_in(ran, f"the sources of commit {THE_COMMIT[:12]} could not be fetched from GitHub: api HTTP 000, api HTTP 000, codeload HTTP 500, codeload HTTP 500")
        self.assertEqual([call.split()[-1].split("/")[2] for call in ran.calls_of("curl ")], ["api.github.com"] * 2 + ["codeload.github.com"] * 2, "two tries at each host")
        self.assertIn("  curl: (22) The requested URL returned error: 500", ran.lines)
        self.assertNotIn(THE_TOKEN_OF_THE_RUN, ran.done.stdout + ran.done.stderr)
        ran = self.fetch(kind="cases", statuses={"api": "000", "codeload": "000"})
        self.stopped_before_the_sign_in(ran, "api HTTP 000, api HTTP 000, codeload HTTP 000, codeload HTTP 000")

    # --- the archive ---------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_an_archive_that_cannot_be_opened_stops_the_run_before_the_sign_in(self):
        for body in (b"<html>an error page that came with a 200</html>", b"", github_zip()[:300]):
            ran = self.fetch(archive=body)
            self.stopped_before_the_sign_in(ran, "the archive cannot be used: it cannot be read: ")

    def test_a_path_that_would_leave_the_folder_is_refused_and_nothing_is_written_outside_it(self):
        for name in (f"{THE_TOP}/src/case-functions/cases/../../../escape.txt", f"{THE_TOP}/../escape.txt", "/absolute/escape.txt", f"{THE_TOP}/src/case-functions/cases/..\\..\\escape.py"):
            ran = self.fetch(archive=github_zip(also={name: b"x"}))
            self.stopped_before_the_sign_in(ran, "a path of the archive would leave the folder")

    def test_an_archive_that_is_not_one_commit_or_lacks_what_the_app_needs_stops_the_run_in_plain_words(self):
        without = {name: content for name, content in CASES_SOURCE_FILES.items() if name != "function_app.py"}
        self.stopped_before_the_sign_in(self.fetch(archive=github_zip(without)), "function_app.py is not in the archive")
        self.stopped_before_the_sign_in(self.fetch(archive=github_zip({"function_app.py": b"#\n", "host.json": b"{}\n"})), "cases/ is not in the archive")
        self.stopped_before_the_sign_in(self.fetch(archive=github_zip(also={"another-folder/README.md": b"x"})), "it is not one commit")
        self.stopped_before_the_sign_in(self.fetch(archive=github_zip({}, rest={})), "function_app.py is not in the archive")

    def test_a_file_of_the_package_that_the_digest_does_not_cover_stops_the_run_because_it_would_ride_unchecked(self):
        for name in ("cases/notes.txt", "cases/__pycache__/loop.cpython-313.pyc", "cases/web/logo.svg", "cases/.py", "cases/web/.json"):  # the last two end in the text of a suffix but have none: the digest passes them over
            ran = self.fetch(archive=github_zip({**CASES_SOURCE_FILES, name: b"x"}))
            self.stopped_before_the_sign_in(ran, "cases/ holds a file that the digest does not cover")

    def test_an_archive_of_more_than_64_MB_stops_the_run_before_the_sign_in_and_the_log_says_the_bytes_and_the_seconds_of_the_download(self):
        archive = github_zip(stored={f"{THE_TOP}/docs/video.bin": b"\0" * (64 << 20)})
        ran = self.fetch(archive=archive)
        self.stopped_before_the_sign_in(ran, "the archive cannot be used: it is more than 64 MB")
        self.assertRegex("\n".join(ran.lines), rf"(?m)^ok: the sources of commit {THE_COMMIT[:12]} are fetched from GitHub: api, {len(archive)} bytes in \d+ s$")

    def test_an_app_file_of_more_than_2_MB_stops_the_run_before_the_sign_in_and_one_of_exactly_2_MB_does_not(self):
        files = {**CASES_SOURCE_FILES, "cases/big.py": b"#" * (2 << 20)}
        ran = self.fetch({"FAKE_AZ_LOGIN": "fail"}, archive=github_zip(files), digest=held_digest(files))  # the run need not go on after the sign-in
        self.assertIn("ok: the app's files are taken from it: 6 files", ran.lines)
        files["cases/big.py"] += b"#"
        self.stopped_before_the_sign_in(self.fetch(archive=github_zip(files), digest=held_digest(files)), "the archive cannot be used: an app file is more than 2 MB")

    def test_files_that_are_not_those_of_the_checkout_stop_the_run_before_the_sign_in_whatever_was_changed(self):
        original = held_digest(CASES_SOURCE_FILES)
        renamed = {("cases/go.py" if name == "cases/loop.py" else name): content for name, content in CASES_SOURCE_FILES.items()}
        for label, files in (("a byte", {**CASES_SOURCE_FILES, "cases/loop.py": b"# loop!\n"}), ("a comment", {**CASES_SOURCE_FILES, "cases/loop.py": b"# the loop\n"}),
                             ("a file added", {**CASES_SOURCE_FILES, "cases/extra.py": b"x = 1\n"}), ("a file missing", {k: v for k, v in CASES_SOURCE_FILES.items() if k != "cases/web/home.py"}),
                             ("the entry file", {**CASES_SOURCE_FILES, "function_app.py": b"import evil\n"}), ("a file renamed", renamed)):
            ran = self.fetch(archive=github_zip(files), digest=original)
            self.stopped_before_the_sign_in(ran, f"the files from GitHub are not those of the workflow's commit (digest {held_digest(files)[:12]}, expected {original[:12]})")
        self.assertNotEqual(held_digest({**CASES_SOURCE_FILES, "cases/loop.py": b"# the loop\n"}), original, "a comment is part of a file that runs, so it is part of the digest")

    def test_the_lock_and_the_host_file_are_those_of_the_request_and_never_those_of_the_archive(self):
        poisoned = {**CASES_SOURCE_FILES, "requirements.txt": b"evil==1.0 \\\n    --hash=sha256:" + b"00" * 32 + b"\n", "host.json": b'{"version": "evil"}\n'}
        ran = self.fetch(archive=github_zip(poisoned))
        self.assertEqual(ran.done.returncode, 0, ran.lines)
        with zipfile.ZipFile(io.BytesIO(ran.posted)) as package:
            self.assertEqual(package.read("requirements.txt"), CASES_SOURCE_FILES["requirements.txt"], "the lock is what anchors the libraries: it never rides on GitHub's word")
            self.assertEqual(package.read("host.json"), CASES_SOURCE_FILES["host.json"])

    # --- the input -------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_three_variables_are_always_set_and_checked_before_anything_runs(self):
        for name, bad in (("PUBLISH_SOURCES_COMMIT", (None, "", "abc", THE_COMMIT[:39], THE_COMMIT.upper(), THE_COMMIT + "0", f"{THE_COMMIT}; touch canary", "$(touch canary)")),
                          ("PUBLISH_SOURCES_REPOSITORY", (None, "", "owner", "owner/", "/name", "owner/name/extra", "owner/..", "owner/.", "ow ner/name", "-owner/name", "owner/name; touch canary",
                                                          "$(touch canary)/x", "a" * 40 + "/name", "owner/" + "n" * 101)),
                          ("PUBLISH_SOURCES_DIGEST", (None, "", "abc", "0" * 63, "0" * 65, "G" * 64, "0" * 63 + "F", "$(touch canary)"))):
            for value in bad:
                self.refused({name: value})
            self.assertIn(name, self.refused({name: "not valid"}).lines[0])

    def test_none_of_the_three_variables_set_is_a_refusal_and_not_another_way(self):
        ran = self.refused({"PUBLISH_SOURCES_COMMIT": None, "PUBLISH_SOURCES_REPOSITORY": None, "PUBLISH_SOURCES_DIGEST": None})
        self.assertIn("PUBLISH_SOURCES_REPOSITORY is not owner/name", ran.lines[0], "the first of them that is wrong is said, and the run goes no further")

    def test_the_lock_and_the_host_file_need_not_be_in_the_archive_because_the_request_carries_them(self):
        files = {name: content for name, content in CASES_SOURCE_FILES.items() if name not in ("requirements.txt", "host.json")}
        ran = self.fetch(archive=github_zip(files))
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""), ran.lines)
        with zipfile.ZipFile(io.BytesIO(ran.posted)) as package:
            self.assertEqual((package.read("requirements.txt"), package.read("host.json")), (CASES_SOURCE_FILES["requirements.txt"], CASES_SOURCE_FILES["host.json"]))