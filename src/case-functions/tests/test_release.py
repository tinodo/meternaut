"""The digest of the app's own files: what is running, as one hash.

It has to be the same for the folder of a build, for the folder that the platform unpacked and for a checkout on any system, and it has to change with every file that is added, removed,
renamed or changed. The deployment sets it as PACKAGE_SHA256 with tools/package-digest.py, which makes it with this module.
"""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from support import APP_ROOT, REPO_ROOT

from cases import release
from cases.release import ReleaseError


def make(folder: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return folder


APP = {"function_app.py": b"import cases\n", "cases/__init__.py": b"", "cases/one.py": b"x = 1\n", "cases/web/two.py": b"y = 2\n", "cases/agents.lock.json": b"{}\n"}


class TheDigest(unittest.TestCase):
    def setUp(self):
        self.folders = []

    def folder(self, files=None):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return make(Path(holder.name), APP if files is None else files)

    def test_it_covers_the_entry_the_python_files_of_the_package_and_its_lock_in_the_order_of_their_paths_and_nothing_else(self):
        folder = self.folder({**APP, "host.json": b"{}", "requirements.txt": b"x", "tests/test_x.py": b"t", "cases/__pycache__/one.cpython-313.pyc": b"c", "cases/notes.md": b"n",
                              ".python_packages/lib/x.py": b"p"})
        self.assertEqual([name for name, _ in release.files_of(folder)], ["cases/__init__.py", "cases/agents.lock.json", "cases/one.py", "cases/web/two.py", "function_app.py"])
        self.assertEqual(release.digest(folder)[1], 5)

    def test_it_is_a_sha256_in_hexadecimal_and_the_same_every_time(self):
        folder = self.folder()
        first = release.digest(folder)
        self.assertRegex(first[0], r"^[0-9a-f]{64}$")
        self.assertEqual(release.digest(folder), first)

    def test_a_folder_that_holds_the_same_files_has_the_same_digest_wherever_it_is(self):
        self.assertEqual(release.digest(self.folder()), release.digest(self.folder()))

    def test_line_ends_do_not_change_it_because_a_checkout_on_windows_has_other_ones(self):
        crlf = {name: data.replace(b"\n", b"\r\n") for name, data in APP.items()}
        self.assertEqual(release.digest(self.folder(crlf)), release.digest(self.folder()))

    def test_every_kind_of_change_changes_it(self):
        base = release.digest(self.folder())[0]
        changes = {
            "a changed file": {**APP, "cases/one.py": b"x = 2\n"},
            "an added file": {**APP, "cases/three.py": b""},
            "a removed file": {k: v for k, v in APP.items() if k != "cases/one.py"},
            "a renamed file": {("cases/uno.py" if k == "cases/one.py" else k): v for k, v in APP.items()},
            "a moved file": {("cases/web/one.py" if k == "cases/one.py" else k): v for k, v in APP.items()},
            "a changed lock": {**APP, "cases/agents.lock.json": b'{"a":1}\n'},
            "a changed entry": {**APP, "function_app.py": b"import evil\n"},
        }
        for what, files in changes.items():
            with self.subTest(what=what):
                self.assertNotEqual(release.digest(self.folder(files))[0], base)

    def test_what_is_not_the_apps_own_does_not_change_it(self):
        base = release.digest(self.folder())[0]
        extra = {**APP, "requirements.txt": b"new", "host.json": b"{}", "cases/__pycache__/x.pyc": b"c", "cases/readme.md": b"n", "tests/a.py": b"t"}
        self.assertEqual(release.digest(self.folder(extra))[0], base)

    def test_a_folder_that_is_not_the_folder_of_the_app_is_an_error(self):
        with self.assertRaises(ReleaseError):
            release.digest(self.folder({"function_app.py": b"x"}))

    def test_an_app_with_no_entry_file_still_has_a_digest_over_its_package(self):
        self.assertEqual(release.digest(self.folder({"cases/one.py": b"x"}))[1], 1)

    def test_the_folder_of_the_app_that_runs_is_the_one_that_holds_the_package_and_the_entry(self):
        self.assertEqual(release.app_folder(), APP_ROOT)
        names = [name for name, _ in release.files_of(APP_ROOT)]
        self.assertIn("function_app.py", names)
        self.assertIn("cases/release.py", names)
        self.assertIn("cases/agents.lock.json", names)
        self.assertFalse([n for n in names if n.startswith("tests/")])

    def test_the_module_imports_nothing_of_the_package_so_that_a_tool_can_load_it_from_its_own_folder(self):
        text = (APP_ROOT / "cases" / "release.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"^from \.|^import cases|^from cases", "no import of the package")


class TheTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("package_digest_tool", REPO_ROOT / "tools" / "package-digest.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def run_tool(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.tool.main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def test_it_prints_the_digest_that_the_app_computes_over_its_own_files(self):
        code, out, err = self.run_tool(str(APP_ROOT))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), release.digest(APP_ROOT)[0])
        self.assertRegex(err, r"^\d+ files$")

    def test_check_says_whether_the_digest_is_the_expected_one_and_exits_that_way(self):
        expected = release.digest(APP_ROOT)[0]
        self.assertEqual(self.run_tool(str(APP_ROOT), "--check", expected)[:2], (0, "the digest is the one expected\n"))
        self.assertEqual(self.run_tool(str(APP_ROOT), "--check", "0" * 64)[:2], (1, "the digest is not the one expected\n"))
        self.assertEqual(self.run_tool(str(APP_ROOT), "--check", "not a digest")[0], 2)

    def test_a_folder_that_is_not_the_folder_of_the_app_exits_2_with_a_plain_message(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, err = self.run_tool(folder)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("is not the folder of the app", err)


if __name__ == "__main__":
    unittest.main()
