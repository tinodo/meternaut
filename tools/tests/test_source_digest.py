"""tools/source-digest.py: the digest of the cases app's own files, which the action cases records as the app setting PACKAGE_SHA256 and tags the app with, and which tools/drift-check.py compares with main.

The digest is of the content, so that it is the same on every machine and for every zip (a zip holds the time of each file). The in-app check of the agent harness (cases/release.py and cases/drift.py,
the control A-RELEASE) works out the same digest over the files that it runs from and holds it against the setting, so the digest of a known folder is pinned here, and a change of the algorithm is a change in
both places: a digest that differs makes that control fail on every release, and pulls the switch of the investigation."""
import hashlib
import importlib.util
import io
import os
import re
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("source_digest", ROOT / "tools" / "source-digest.py")
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)

COVERED = {
    "function_app.py": b"import azure.functions as func\n",
    "cases/__init__.py": b"",
    "cases/run.py": b"def run():\n    return 1\n",
    "cases/sub/deep.py": b"x = 1\n",
    "cases/agents.lock.json": b'{"agents": {}}\n',
}
NOT_COVERED = {
    "host.json": b'{"version": "2.0"}\n',
    "requirements.txt": b"azure-functions==2.3.0 --hash=sha256:00\n",
    "cases/notes.md": b"not covered\n",
    "cases/__pycache__/run.cpython-313.pyc": b"x",
    "cases/run.pyc": b"y",
    "tests/test_run.py": b"t\n",
    ".funcignore": b"v\n",
}
FILES = {**COVERED, **NOT_COVERED}
# The digest of this very folder as the app's own module (cases/release.py of the agent harness) makes it: the two have to give the same one.
GOLDEN = "1c7b21ba90034dc838aa31565f885a9283287da8b296b44775474a427c24dfd1"
RELEASE = ROOT / "src" / "case-functions" / "cases" / "release.py"


def make(root: Path, files=FILES):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def expected(files=COVERED) -> str:
    lines = "".join(f"{name}\0{hashlib.sha256(content).hexdigest()}\n" for name, content in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


class TheAlgorithm(unittest.TestCase):
    def test_the_digest_is_the_sha256_of_the_sorted_lines_of_path_and_file_digest_of_the_entry_and_the_python_and_json_files_of_the_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            self.assertEqual([path for _, path in sd.manifest(Path(tmp))], ["cases/__init__.py", "cases/agents.lock.json", "cases/run.py", "cases/sub/deep.py", "function_app.py"])
            self.assertEqual(sd.digest(Path(tmp)), expected())

    def test_the_digest_of_a_known_folder_is_pinned_so_that_the_app_s_own_module_gives_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            self.assertEqual(sd.digest(Path(tmp)), GOLDEN)
            self.assertEqual(sd.manifest(Path(tmp)), [(hashlib.sha256(COVERED[name]).hexdigest(), name) for name in sorted(COVERED)],
                             "the manifest is the digest of each file and its path, in the order of the paths")

    def test_line_ends_do_not_change_it_because_a_checkout_on_windows_has_other_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp), {name: content.replace(b"\n", b"\r\n") for name, content in FILES.items()})
            self.assertEqual(sd.digest(Path(tmp)), GOLDEN)

    def test_what_is_not_the_apps_own_code_is_left_out_and_the_time_of_a_file_does_not_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make(root, COVERED)
            first = sd.digest(root)
            make(root, NOT_COVERED)
            old = time.time() - 86400 * 400
            os.utime(root / "cases" / "run.py", (old, old))
            self.assertEqual(sd.digest(root), first, "the lock of the libraries, the host file, a cache, a test, a note and a file outside the package change nothing, and neither does a file's time")

    def test_a_changed_byte_a_renamed_a_moved_a_removed_and_an_added_file_each_change_the_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make(root, COVERED)
            seen = {sd.digest(root)}
            run = root / "cases" / "run.py"
            run.write_bytes(b"def run():\n    return 2\n")
            seen.add(sd.digest(root))
            run.write_bytes(COVERED["cases/run.py"])
            run.rename(root / "cases" / "go.py")
            seen.add(sd.digest(root))
            (root / "cases" / "go.py").rename(root / "cases" / "sub" / "run.py")
            seen.add(sd.digest(root))
            (root / "cases" / "sub" / "run.py").rename(run)
            (root / "cases" / "extra.py").write_bytes(b"")
            seen.add(sd.digest(root))
            (root / "cases" / "extra.py").unlink()
            run.unlink()
            seen.add(sd.digest(root))
            (root / "cases" / "agents.lock.json").write_bytes(b'{"agents": {"a": 1}}\n')
            seen.add(sd.digest(root))
            (root / "function_app.py").write_bytes(b"import evil\n")
            seen.add(sd.digest(root))
        self.assertEqual(len(seen), 8)

    def test_an_app_with_no_entry_file_has_a_digest_over_its_package_and_a_folder_that_is_not_the_app_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sd.Problem) as stopped:
                sd.digest(Path(tmp))
            self.assertIn("cases/ is not in", str(stopped.exception))
            make(Path(tmp), {"function_app.py": b"", "host.json": b"", "requirements.txt": b""})
            with self.assertRaises(sd.Problem):
                sd.digest(Path(tmp))
            make(Path(tmp), {"cases/one.py": b"x"})
            self.assertEqual(len(sd.manifest(Path(tmp))), 2)
            (Path(tmp) / "function_app.py").unlink()
            self.assertEqual(len(sd.manifest(Path(tmp))), 1)
        with self.assertRaises(sd.Problem):
            sd.digest(Path(tmp) / "nowhere")


class TheCommandLine(unittest.TestCase):
    def test_it_prints_64_hex_digits_or_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(sd.main([tmp]), 0)
            self.assertEqual(out.getvalue(), GOLDEN + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(sd.main([tmp, "--manifest"]), 0)
            lines = out.getvalue().splitlines()
            self.assertEqual(len(lines), len(COVERED))
            for line in lines:
                self.assertRegex(line, r"^[0-9a-f]{64}  [a-z_/.]+$")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(sd.main([str(Path(tmp) / "nowhere")]), 2)
            self.assertIn("error:", err.getvalue())


class TheRepository(unittest.TestCase):
    def test_the_files_that_the_digest_covers_are_among_those_that_the_build_of_the_package_copies(self):
        script = (ROOT / "tools" / "build-function-app.sh").read_text(encoding="utf-8")
        copied = re.search(r'cp -r (.+) "\$build/"', script).group(1)
        self.assertIn(f'"$source_dir/{sd.ENTRY_FILE}"', copied)
        self.assertIn('"$source_dir/$package"', copied)
        self.assertEqual(sd.CODE_PACKAGE, "cases")
        self.assertIn("-name '__pycache__'", script, "the build leaves the compiled caches out, and so does the digest")

    def test_the_real_app_has_a_digest_and_its_manifest_holds_the_entry_and_the_package_and_no_test_and_no_lock_of_the_libraries(self):
        manifest = sd.manifest(ROOT / "src" / "case-functions")
        paths = [path for _, path in manifest]
        for needed in ("function_app.py", "cases/__init__.py"):
            self.assertIn(needed, paths)
        self.assertFalse([p for p in paths if p.startswith("tests/") or "__pycache__" in p or p.endswith(".pyc") or p in ("host.json", "requirements.txt")])
        self.assertRegex(sd.digest(ROOT / "src" / "case-functions"), r"^[0-9a-f]{64}$")

    @unittest.skipUnless(RELEASE.is_file(), "cases/release.py (the agent harness) is not in the repository yet: the pinned digest above stands for it until then")
    def test_the_app_s_own_module_gives_the_same_digest_for_the_real_app_and_for_the_known_folder(self):
        release_spec = importlib.util.spec_from_file_location("release_of_the_app", RELEASE)
        release = importlib.util.module_from_spec(release_spec)
        release_spec.loader.exec_module(release)
        self.assertEqual(release.digest(ROOT / "src" / "case-functions")[0], sd.digest(ROOT / "src" / "case-functions"))
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            self.assertEqual(release.digest(Path(tmp))[0], sd.digest(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
