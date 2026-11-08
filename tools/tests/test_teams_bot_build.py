"""tools/build-teams-bot.sh: the package of the Teams bot's function app has the bot's entry in the place of function_app.py and the cases app's code package behind it, and no other entry. It is run in
the mode that zips the sources (FUNCTION_APP_SOURCES_ONLY=1: nothing is installed, so no wheels and no network are needed), with the Git bash that the other build tests find."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "case-functions"


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


def build(script, *arguments, cwd=ROOT):
    return subprocess.run([BASH, "-e", "-o", "pipefail", posix(script), *arguments], capture_output=True, text=True, cwd=cwd, env={**os.environ, "FUNCTION_APP_SOURCES_ONLY": "1"})


def package_files():
    return sorted(f"cases/{path.relative_to(SOURCE / 'cases').as_posix()}" for path in (SOURCE / "cases").rglob("*") if path.is_file() and "__pycache__" not in path.parts)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheBotsPackage(unittest.TestCase):
    """One build serves the tests that read the zip. It runs over a stage that an earlier build left behind, which the script makes again."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        stage = base / "bot-source"
        stage.mkdir()
        (stage / "stale.txt").write_text("left by an earlier build", encoding="utf-8")
        (stage / "function_app.py").write_text("raise SystemExit('a stale entry')\n", encoding="utf-8")
        cls.done = build(ROOT / "tools" / "build-teams-bot.sh", posix(base / "bot"), posix(base / "bot.zip"))
        cls.files, cls.names = {}, []
        if (base / "bot.zip").exists():
            with zipfile.ZipFile(base / "bot.zip") as archive:
                cls.names = archive.namelist()
                cls.files = {name: archive.read(name) for name in cls.names if not name.endswith("/")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_build_ends_well(self):
        self.assertEqual(self.done.returncode, 0, self.done.stderr)

    def test_the_zip_holds_the_bots_entry_as_function_app_and_the_cases_package_and_nothing_else(self):
        self.assertEqual(sorted(self.files), sorted(["function_app.py", "host.json", "requirements.txt", *package_files()]))
        self.assertEqual(self.files["function_app.py"], (SOURCE / "teams_function_app.py").read_bytes(), "the entry of the package is the bot's")
        self.assertNotEqual(self.files["function_app.py"], (SOURCE / "function_app.py").read_bytes(), "and it is not the cases app's")
        self.assertEqual(self.files["requirements.txt"], (SOURCE / "requirements.txt").read_bytes(), "the same hash-locked libraries")
        self.assertEqual(json.loads(self.files["host.json"])["extensions"]["http"]["routePrefix"], "", "the messaging endpoint is /api/messages and not /api/api/messages")

    def test_what_an_earlier_build_left_in_the_stage_does_not_ride_along(self):
        self.assertNotIn("stale.txt", self.names)
        self.assertNotIn(b"a stale entry", self.files.get("function_app.py", b""))

    def test_the_package_has_no_tests_no_second_entry_no_caches_and_no_libraries_in_this_mode(self):
        self.assertFalse([n for n in self.names if n.startswith("tests/") or "/tests/" in n], "the tests are left out")
        self.assertNotIn("teams_function_app.py", self.names, "the entry is not there twice")
        self.assertFalse([n for n in self.names if "__pycache__" in n or n.startswith(".python_packages")])
        self.assertEqual([n for n in self.names if n.endswith("function_app.py")], ["function_app.py"], "one entry")

    def test_the_entry_in_the_package_declares_the_two_functions_of_the_bot_and_none_of_the_cases_app(self):
        entry = self.files["function_app.py"].decode("utf-8")
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', entry)), ["teams-messages", "teams-offer"])
        self.assertNotIn("{*route}", entry, "no catch-all route: the console's page is not in this app")
        cases_functions = re.findall(r'function_name\(name="([a-z-]+)"\)', (SOURCE / "function_app.py").read_text(encoding="utf-8"))
        self.assertTrue(cases_functions)
        for name in cases_functions:
            self.assertNotIn(f'name="{name}"', entry, f"the cases app's function {name} is not in the public app")


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheBuildScriptRefuses(unittest.TestCase):
    def test_both_arguments_are_needed(self):
        script = ROOT / "tools" / "build-teams-bot.sh"
        for arguments, said in (((), "the build directory is the first argument"), (("somewhere",), "the zip file is the second argument")):
            done = build(script, *arguments)
            self.assertEqual(done.returncode, 1, arguments)
            self.assertIn(said, done.stderr)

    def test_a_missing_source_stops_the_build_before_anything_is_made(self):
        for missing in ("teams_function_app.py", "cases/teams.py"):
            with tempfile.TemporaryDirectory() as tmp:
                tools = Path(tmp) / "tools"
                tools.mkdir()
                for name in ("build-teams-bot.sh", "build-function-app.sh"):
                    shutil.copyfile(ROOT / "tools" / name, tools / name)
                source = Path(tmp) / "src" / "case-functions"
                (source / "cases").mkdir(parents=True)
                for name in ("teams_function_app.py", "host.json", "requirements.txt", "cases/teams.py"):
                    if name != missing:
                        (source / name).write_text("x\n", encoding="utf-8")
                done = build(tools / "build-teams-bot.sh", posix(Path(tmp) / "bot"), posix(Path(tmp) / "bot.zip"), cwd=tmp)
                self.assertEqual(done.returncode, 1, missing)
                self.assertIn(f"{missing} is not there", done.stderr)
                self.assertFalse((Path(tmp) / "bot").exists() or (Path(tmp) / "bot-source").exists() or (Path(tmp) / "bot.zip").exists(), "nothing was staged or built")


if __name__ == "__main__":
    unittest.main()
