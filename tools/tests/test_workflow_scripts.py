import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
PRINCIPAL = "5a1c0de0-0000-4000-8000-0000000000de"
CLIENT = "11111111-2222-3333-4444-555555555555"


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def step_script(name):
    """The `run:` script of the step with this name, as the runner would write it to a file."""
    block = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", WORKFLOW)
    assert block, name
    run = re.search(r"(?ms)^        run: \|\n(.*)", block.group(1))
    assert run, name
    return textwrap.dedent(run.group(1))


AZ = """#!/bin/bash
case "$*" in
  *"identity list"*) printf '%s' "$FAKE_IDENTITY" ;;
  *"rest "*) printf '%s' "$FAKE_LOGGERS" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

PYTHON3 = """#!/bin/bash
if [ "$2" = "build" ]; then
  echo "build principal=${GATEWAY_PRINCIPAL_ID-unset} client=${GATEWAY_CLIENT_ID-unset} fragments=${RECORDING_FRAGMENTS-unset} preview=$([[ " $* " == *" --preview "* ]] && echo yes || echo no)" >> "$FAKE_LOG"
  printf 'gateway_subscription=sub1\\ngateway_resource_group=rg1\\nidentity_name=id-meternaut-gateway\\n'
else
  echo "check $*" >> "$FAKE_LOG"
fi
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class WorkOutTheSettings(unittest.TestCase):
    """The shell of the step that decides what the later steps ask for, run against stand-ins for the Azure CLI and the parameter builder."""

    def run_step(self, identity, loggers):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in (("az", AZ), ("python3", PYTHON3)):
                path = bin_dir / name
                path.write_text(body, encoding="utf-8", newline="\n")
                path.chmod(path.stat().st_mode | stat.S_IEXEC)
            script = tmp / "step.sh"
            script.write_text(step_script("Work out the settings"), encoding="utf-8", newline="\n")
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            (tmp / "out.txt").write_text("", encoding="utf-8")
            env = {**os.environ,
                   "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}",
                   "FAKE_IDENTITY": identity, "FAKE_LOGGERS": loggers, "FAKE_LOG": log.as_posix(),
                   "GITHUB_OUTPUT": (tmp / "out.txt").as_posix(), "RUNNER_TEMP": tmp.as_posix(),
                   "GATEWAY_RESOURCE_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg1/providers/Microsoft.ApiManagement/service/apim1"}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=env, cwd=ROOT)
            return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "out.txt").read_text(encoding="utf-8")

    def builds(self, lines):
        return [line for line in lines if line.startswith("build ")]

    def test_the_identity_on_one_line_and_both_loggers_present_turns_the_fragments_on(self):
        done, lines, out = self.run_step(f"{PRINCIPAL}\t{CLIENT}", "appinsights-logger\nusage-eventhub-logger\npii-usage-eventhub-logger\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines), ["build principal=unset client=unset fragments=unset preview=yes",
                                              f"build principal={PRINCIPAL} client={CLIENT} fragments=true preview=no"])
        self.assertIn("gateway_subscription=sub1", out)

    def test_the_identity_on_two_lines_is_read_the_same_way(self):
        done, lines, _ = self.run_step(f"{PRINCIPAL}\n{CLIENT}", "appinsights-logger\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.builds(lines)[1], f"build principal={PRINCIPAL} client={CLIENT} fragments=false preview=no")

    def test_one_logger_is_not_enough(self):
        for loggers in ("usage-eventhub-logger\n", "pii-usage-eventhub-logger\n", "", "usage-eventhub-logger-2\npii-usage-eventhub-logger\n"):
            done, lines, _ = self.run_step(f"{PRINCIPAL}\t{CLIENT}", loggers)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("fragments=false", self.builds(lines)[1], loggers)

    def test_without_the_identity_only_the_preview_is_built(self):
        for identity in ("", "None", PRINCIPAL):
            done, lines, _ = self.run_step(identity, "usage-eventhub-logger\npii-usage-eventhub-logger\n")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(self.builds(lines), ["build principal=unset client=unset fragments=unset preview=yes"], identity)
            self.assertIn("does not exist yet", done.stdout)

    def test_every_parameter_file_is_checked_against_its_template(self):
        done, lines, _ = self.run_step(f"{PRINCIPAL}\t{CLIENT}", "")
        checks = [line for line in lines if line.startswith("check ")]
        labels = [re.search(r"--label (\S+)", line).group(1) for line in checks]
        self.assertEqual(labels, ["environment", "logger", "eventhub-loggers", "kit", "recording", "contract", "cases"])


STAND_IN_PYTHON = """#!/bin/bash
if [ "$1" = "--version" ]; then echo "Python $FAKE_PYTHON"; exit 0; fi
if [ "$1" = "-c" ]; then
  if [ "$FAKE_PYTHON" = "3.13.0" ]; then exit 0; fi
  exit 1
fi
echo "python3 $*" >> "$FAKE_LOG"
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class BuildTheFunctionPackage(unittest.TestCase):
    """tools/build-function-app.sh against a stand-in for python3: what it refuses, and the exact install that it asks for."""

    def run_script(self, python_version, arguments=("usage-functions", "usage")):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            python3 = bin_dir / "python3"
            python3.write_text(STAND_IN_PYTHON, encoding="utf-8", newline="\n")
            python3.chmod(python3.stat().st_mode | stat.S_IEXEC)
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            build = tmp / "build"
            env = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_PYTHON": python_version, "FAKE_LOG": log.as_posix()}
            done = subprocess.run([BASH, "-e", "-o", "pipefail", (ROOT / "tools" / "build-function-app.sh").as_posix(), *arguments, build.as_posix()],
                                  capture_output=True, text=True, env=env, cwd=ROOT)
            copied = sorted(p.name for p in build.iterdir()) if build.exists() else []
            return done, log.read_text(encoding="utf-8").splitlines(), copied

    def test_another_python_than_3_13_stops_it_before_anything_is_built(self):
        for version in ("3.12.3", "3.14.0", "3.11.9"):
            done, calls, copied = self.run_script(version)
            self.assertEqual(done.returncode, 1, version)
            self.assertIn("build with Python 3.13", done.stderr)
            self.assertIn(f"Python {version}", done.stderr)
            self.assertEqual((calls, copied), ([], []), "no download and no copy before the refusal")

    def test_python_3_13_installs_only_wheels_of_the_lock_for_linux_and_checks_their_hashes(self):
        done, calls, copied = self.run_script("3.13.0")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(copied, ["function_app.py", "host.json", "requirements.txt", "usage"], "the app's files; the stand-in pip makes no target directory")
        (install,) = calls
        for flag in ("-m pip install", "--require-hashes", "--only-binary=:all:", "--platform manylinux2014_x86_64", "--platform manylinux_2_28_x86_64",
                     "--implementation cp", "--python-version 3.13", "--no-compile", "/.python_packages/lib/site-packages", "src/usage-functions/requirements.txt"):
            self.assertIn(flag, install)
        for word in ("--index-url", "--extra-index-url", "--trusted-host", "--no-deps"):
            self.assertNotIn(word, install, word)

    def test_the_cases_app_is_built_from_its_own_lock(self):
        done, calls, copied = self.run_script("3.13.0", arguments=("case-functions", "cases"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(copied, ["cases", "function_app.py", "host.json", "requirements.txt"])
        (install,) = calls
        self.assertIn("src/case-functions/requirements.txt", install)
        self.assertNotIn("usage-functions", install)

    def test_names_that_leave_the_src_folder_or_the_plain_form_are_refused_before_anything_is_built(self):
        for arguments in (("../tools", "usage"), ("usage-functions", "usage/../x"), ("Usage-Functions", "usage"), ("usage-functions", "Usage"), ("", "usage")):
            done, calls, copied = self.run_script("3.13.0", arguments=arguments)
            self.assertNotEqual(done.returncode, 0, arguments)
            self.assertEqual((calls, copied), ([], []), arguments)


if __name__ == "__main__":
    unittest.main()
