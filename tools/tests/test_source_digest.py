"""tools/source-digest.py: the digest of the cases app's own files, which the action cases records as the app setting PACKAGE_SHA256 and tags the app with, and which tools/drift-check.py compares with main.

The digest is of the content, so that it is the same on every machine and for every zip (a zip holds the time of each file). The in-app check of the agent harness (cases/drift.py) has to work out the same
digest over its own files, so the lines of a known folder are pinned here: a change of the algorithm is a change in both places."""
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

FILES = {
    "function_app.py": b"import azure.functions as func\n",
    "host.json": b'{"version": "2.0"}\n',
    "requirements.txt": b"azure-functions==2.3.0 --hash=sha256:00\n",
    "cases/__init__.py": b"",
    "cases/run.py": b"def run():\n    return 1\n",
    "cases/sub/deep.py": b"x = 1\n",
}


def make(root: Path, files=FILES):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def expected(files=FILES) -> str:
    lines = "".join(f"{name}\0{hashlib.sha256(content).hexdigest()}\n" for name, content in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


class TheAlgorithm(unittest.TestCase):
    def test_the_digest_is_the_sha256_of_the_sorted_lines_of_path_and_file_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            self.assertEqual(sd.digest(Path(tmp)), expected())

    def test_the_lines_of_a_known_folder_are_pinned_so_that_the_app_can_work_out_the_same(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            self.assertEqual(sd.manifest(Path(tmp)), sorted(((hashlib.sha256(content).hexdigest(), name) for name, content in FILES.items()), key=lambda entry: entry[1]),
                             "the manifest is the digest of each file and its path, in the order of the paths")
            self.assertEqual(sd.digest(Path(tmp)), "483136cb3b422fa4d8f148758f75534a02463d9c5a45594eba27432fd1f056d9",
                             "the digest of this very folder: a copy of the algorithm in the app has to give the same")

    def test_the_caches_and_the_tests_are_left_out_and_the_time_of_a_file_does_not_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make(root)
            first = sd.digest(root)
            make(root, {"cases/__pycache__/run.cpython-313.pyc": b"x", "cases/run.pyc": b"y", "tests/test_run.py": b"z", "README.md": b"w", ".funcignore": b"v"})
            old = time.time() - 86400 * 400
            os.utime(root / "cases" / "run.py", (old, old))
            self.assertEqual(sd.digest(root), first, "a cache, a test and a file outside the package change nothing, and neither does a file's time")

    def test_a_changed_byte_a_renamed_file_and_an_added_file_each_change_the_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make(root)
            base = sd.digest(root)
            (root / "cases" / "run.py").write_bytes(b"def run():\n    return 2\n")
            changed = sd.digest(root)
            (root / "cases" / "run.py").write_bytes(FILES["cases/run.py"])
            (root / "cases" / "run.py").rename(root / "cases" / "go.py")
            renamed = sd.digest(root)
            (root / "cases" / "go.py").rename(root / "cases" / "run.py")
            (root / "cases" / "extra.py").write_bytes(b"")
            added = sd.digest(root)
        self.assertEqual(len({base, changed, renamed, added}), 4)

    def test_a_folder_that_is_not_the_app_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sd.Problem) as stopped:
                sd.digest(Path(tmp))
            self.assertIn("is not in", str(stopped.exception))
            make(Path(tmp), {"function_app.py": b"", "host.json": b"", "requirements.txt": b""})
            with self.assertRaises(sd.Problem) as stopped:
                sd.digest(Path(tmp))
            self.assertIn("cases/", str(stopped.exception))
        with self.assertRaises(sd.Problem):
            sd.digest(Path(tmp) / "nowhere")


class TheCommandLine(unittest.TestCase):
    def test_it_prints_64_hex_digits_or_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(sd.main([tmp]), 0)
            self.assertEqual(out.getvalue(), expected() + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(sd.main([tmp, "--manifest"]), 0)
            lines = out.getvalue().splitlines()
            self.assertEqual(len(lines), len(FILES))
            for line in lines:
                self.assertRegex(line, r"^[0-9a-f]{64}  [a-z_/.]+$")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(sd.main([str(Path(tmp) / "nowhere")]), 2)
            self.assertIn("error:", err.getvalue())


class TheRepository(unittest.TestCase):
    def test_the_files_are_exactly_those_that_the_build_of_the_package_copies(self):
        script = (ROOT / "tools" / "build-function-app.sh").read_text(encoding="utf-8")
        copied = re.search(r'cp -r (.+) "\$build/"', script).group(1)
        self.assertEqual(re.findall(r'"\$source_dir/(\$?[\w.]+)"', copied), [*sd.TOP_LEVEL_FILES, "$package"])
        self.assertEqual(sd.CODE_PACKAGE, "cases")
        self.assertIn("-name '__pycache__'", script, "the build leaves the compiled caches out, and so does the digest")

    def test_the_real_app_has_a_digest_and_its_manifest_names_the_four_things_that_the_build_copies_and_no_test(self):
        manifest = sd.manifest(ROOT / "src" / "case-functions")
        paths = [path for _, path in manifest]
        for needed in ("function_app.py", "host.json", "requirements.txt", "cases/__init__.py"):
            self.assertIn(needed, paths)
        self.assertFalse([p for p in paths if p.startswith("tests/") or "__pycache__" in p or p.endswith(".pyc")])
        self.assertRegex(sd.digest(ROOT / "src" / "case-functions"), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
