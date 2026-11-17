"""tools/strip-sources.py: the comments and the text of the docstrings are taken out of the sources that the Operator receives, and nothing else changes.

The files are the code of the app that runs in the Operator's request-sized package (docs/proposals/27-package-without-comments.md). What is held here: the same tree and the same lines for every file
of the real app, a string that is data survives, every module of the stripped copy compiles and imports, the digests that the lock holds are the same for the stripped copy (the one trap), and a file that
cannot be stripped stops the pack with plain words and changes nothing.
"""
import ast
import compileall
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import tokenize
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "case-functions"
spec = importlib.util.spec_from_file_location("strip_sources_under_test", ROOT / "tools" / "strip-sources.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def without_docstrings(text: str) -> str:
    """The syntax tree of the text with the text of every docstring replaced by an empty string, worked out here and not by the tool."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ""
    return ast.dump(tree)


def lines_of(text: str) -> list:
    """Every code object of the text (the module, each class body, each function) with its first line and the line of each of its instructions: what a traceback points at."""
    found = []

    def walk(code):
        found.append((code.co_qualname, code.co_firstlineno, [line for _, _, line in code.co_lines()]))
        for constant in code.co_consts:
            if hasattr(constant, "co_code"):
                walk(constant)

    walk(compile(text, "x.py", "exec"))
    return found


def comments_of(text: str) -> list:
    return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline) if token.type == tokenize.COMMENT]


SAMPLES = {
    "a hash in a string is data": ('a = "# not a comment"\nb = \'# not a comment either\'  # but this is one\nc = f"{a}  # {1 + 1} still data"\nd = f"{a!r:#>10}"   # a hash in a format spec\ne = "a" "# b"  # joined\n',
                                   'a = "# not a comment"\nb = \'# not a comment either\'\nc = f"{a}  # {1 + 1} still data"\nd = f"{a!r:#>10}"\ne = "a" "# b"\n'),
    "a multi-line string that is data": ('SQL = """\nselect 1  # not a comment\n"""  # a comment\nTEXT = """\n    indented\n"""\n', 'SQL = """\nselect 1  # not a comment\n"""\nTEXT = """\n    indented\n"""\n'),
    "a string that is not the first statement": ('import os\n"""Not a docstring: an import is the first statement."""\n\n\ndef f():\n    x = 1\n    """Nor this one."""\n    return x\n\n\nclass A:\n    y = 1\n    """Nor this."""\n',
                                                 None),
    "a class that has only a docstring": ('class Marker:\n    """Only a docstring.\n\n    On three lines."""\n\n\nvalue = 1  # after\n', 'class Marker:\n    ""\n\n\n\n\nvalue = 1\n'),
    "a lambda": ("f = lambda x: x + 1  # adds one\ng = (lambda: '#')()  # data\n", "f = lambda x: x + 1\ng = (lambda: '#')()\n"),
    "non-ASCII text in a docstring, a comment and the code": ('def café(ü="é"):\n    """Ça va très bien — 你好 😀."""\n    return ü + "é"  # commentaire ünïcode 😀\n\n\nclass Ü: """Docstring after non-ASCII."""\nz = "é"  # é\n',
                                                              'def café(ü="é"):\n    ""\n    return ü + "é"\n\n\nclass Ü: ""\nz = "é"\n'),
    "a one-line function and a statement after the docstring": ('def f(): """doc"""; return "é"  # c\n"""Not the first."""; x = 1\n', 'def f(): ""; return "é"\n"""Not the first."""; x = 1\n'),
    "a docstring that has code after it on its last line is left as it is": ('def f():\n    """one\n    two"""; return 1\n', None),
    "a module docstring before a future import": ('"""The module."""\nfrom __future__ import annotations\n\n\ndef f(a: int) -> int:\n    return a  # same\n', '""\nfrom __future__ import annotations\n\n\ndef f(a: int) -> int:\n    return a\n'),
    "decorators, continuations and nested docstrings": ("@decorator  # why\n# between\n@other(\n    1,  # one\n    2,\n)\nasync def g():\n    '''Single quotes.'''\n    value = 1 + \\\n        2  # continued\n\n    def inner():\n        \"\"\"Nested.\"\"\"\n        return value\n\n    return inner\n",
                                                       "@decorator\n\n@other(\n    1,\n    2,\n)\nasync def g():\n    \"\"\n    value = 1 + \\\n        2\n\n    def inner():\n        \"\"\n        return value\n\n    return inner\n"),
    "a raw docstring": ('def f():\n    r"""A raw \\d docstring."""\n    return 1\n', 'def f():\n    ""\n    return 1\n'),
    "a docstring in parentheses, over lines": ('def f():\n    (\n        "a"\n        "b"\n    )\n    return 1\n\n\ndef g():\n    ("""doc""")\n    return 2\n', 'def f():\n    ""\n\n\n\n    return 1\n\n\ndef g():\n    ""\n    return 2\n'),
    "a comment inside a replacement field": ('x = f"""{\n    1 + 1  # a comment of the field\n}"""\n', 'x = f"""{\n    1 + 1  \n}"""\n'),
    "a comment in the braces of an f-string with an =, where the white space before it is text": ('a = 1\nx = f"""{\n    a =  # the comment\n}"""\ny = f"""{a = # c\n}"""\nw = f"""{\n    f\'{a}\'  # nested\n}"""\nv = f"{a}"  # the f-string is over\n',
                                                                                                'a = 1\nx = f"""{\n    a =  \n}"""\ny = f"""{a = \n}"""\nw = f"""{\n    f\'{a}\'  \n}"""\nv = f"{a}"\n'),
    "no new line at the end": ("x = 1  # c", "x = 1"),
    "a comment and nothing else": ("# only a comment\n", "\n"),
    "nothing": ("", ""),
    "carriage returns": ("def f():\r\n    return 1  # c\r\n", "def f():\n    return 1\n"),
}


class TheStrip(unittest.TestCase):
    def holds(self, source: str) -> str:
        result = ss.strip(source)
        ss.check(source, result)
        compile(result, "x.py", "exec")
        text = source.replace("\r\n", "\n")
        self.assertEqual(result.count("\n"), text.count("\n"), "every line is where it was")
        self.assertEqual(without_docstrings(result), without_docstrings(text), "the same tree, whatever the docstrings say")
        self.assertEqual(lines_of(result), lines_of(text), "the same code on the same lines")
        self.assertEqual(ss.strip(result), result, "stripping what is stripped changes nothing")
        self.assertEqual(ss.strip(source), result, "the same text gives the same text")
        return result

    def test_each_sample_keeps_its_code_and_loses_its_comments_and_the_text_of_its_docstrings(self):
        for name, (source, expected) in SAMPLES.items():
            with self.subTest(name):
                result = self.holds(source)
                self.assertEqual(comments_of(result), [])
                self.assertEqual(result, source if expected is None else expected)

    def test_a_string_that_is_data_has_the_same_value_before_and_after(self):
        for name in ("a hash in a string is data", "a multi-line string that is data", "a comment inside a replacement field", "a comment in the braces of an f-string with an =, where the white space before it is text"):
            with self.subTest(name):
                source = SAMPLES[name][0]
                before, after = {}, {}
                exec(compile(source, "x.py", "exec"), before)
                exec(compile(ss.strip(source), "x.py", "exec"), after)
                self.assertEqual({k: v for k, v in before.items() if k != "__builtins__"}, {k: v for k, v in after.items() if k != "__builtins__"})

    def test_a_docstring_becomes_an_empty_string_and_keeps_the_lines_that_its_text_took(self):
        self.assertEqual(ss.strip('def f():\n    """One.\n\n    Two."""\n    return 1\n'), 'def f():\n    ""\n\n\n    return 1\n')
        self.assertEqual(ss.strip('"""A\nmodule."""\nx = 1\n'), '""\n\nx = 1\n')

    def test_the_column_of_the_syntax_tree_counts_bytes_and_the_cut_counts_characters(self):
        result = self.holds('x = "ééé"; y = """ààà"""; z = 1  # é\n')
        self.assertEqual(result, 'x = "ééé"; y = """ààà"""; z = 1\n')
        self.assertEqual(self.holds('class Ü: """é"""; pass  # ç\n'), 'class Ü: ""; pass\n')


class TheCheck(unittest.TestCase):
    GOOD = 'def f():\n    """Doc."""\n    return "a"  # c\n\n\nx = 1\n'

    def test_a_result_that_is_not_the_text_without_its_comments_and_docstrings_is_refused_in_words(self):
        good = ss.strip(self.GOOD)
        ss.check(self.GOOD, good)
        ss.check(self.GOOD, self.GOOD)
        for what, result, said in (("a changed string", good.replace('"a"', '"b"'), "the code changed"), ("a changed number", good.replace("x = 1", "x = 2"), "the code changed"),
                                   ("a lost line", good.replace("\n\n\n", "\n\n"), "the number of lines changed"), ("a statement on another line", good.replace("\n\n\nx = 1\n", "\n\nx = 1\n\n"), "a statement moved to another line")):
            with self.subTest(what):
                with self.assertRaises(ss.Problem) as raised:
                    ss.check(self.GOOD, result)
                self.assertIn(said, str(raised.exception))

    def test_the_white_space_before_a_comment_in_the_braces_of_an_f_string_with_an_equals_sign_is_text_that_python_keeps_so_the_tool_keeps_it(self):
        source = 'a = 1\nx = f"""{\n    a =  # the comment\n}"""\n'
        self.assertEqual(ast.parse(source).body[1].value.values[0].value, "\n    a =  \n", "Python 3.12 and 3.13 keep the two spaces in the text of the f-string and leave the comment out of it")
        with self.assertRaises(ss.Problem) as raised:
            ss.check(source, 'a = 1\nx = f"""{\n    a =\n}"""\n')
        self.assertIn("the code changed", str(raised.exception), "a result that cut the two spaces is not the same code")
        self.assertEqual(ss.strip(source), 'a = 1\nx = f"""{\n    a =  \n}"""\n')

    def test_a_line_end_that_python_reads_and_the_tool_does_not_is_refused(self):
        with self.assertRaises(ss.Problem) as raised:
            ss.strip("x = 1\ry = 2\n")
        self.assertIn("bare carriage return", str(raised.exception))

    def test_a_file_that_is_not_python_or_not_utf8_is_refused_with_words_for_a_person(self):
        for data, said in ((b"def f(:\n", "could not be stripped"), (b"\xff\xfe\x00", "not UTF-8"), (b"if 1:\n  x\n y\n", "could not be stripped")):
            with self.subTest(data=data):
                with self.assertRaises(ss.Problem) as raised:
                    ss.stripped(data)
                self.assertIn(said, str(raised.exception))


class TheFolder(unittest.TestCase):
    FILES = {"function_app.py": b'"""Entry."""\nimport cases  # the package\n', "cases/__init__.py": b"", "cases/one.py": b'def one():\n    """One."""\n    return 1  # one\n', "cases/note.json": b'{"a": "# kept"}\n',
             "cases/__pycache__/one.cpython-313.pyc": b"\x00\x01"}

    def make(self, root: Path, files=None) -> Path:
        for name, data in (files or self.FILES).items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
        return root

    def snapshot(self, root: Path) -> dict:
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}

    def test_every_python_file_under_the_folder_is_stripped_in_place_and_nothing_else_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make(Path(tmp))
            count, before, after = ss.strip_folder(root)
            self.assertEqual(count, 3)
            self.assertEqual(self.snapshot(root), {**self.FILES, "function_app.py": b'""\nimport cases\n', "cases/one.py": b'def one():\n    ""\n    return 1\n'})
            self.assertEqual((before, after), (sum(len(self.FILES[n]) for n in self.FILES if n.endswith(".py")), len(b'""\nimport cases\n') + len(b'def one():\n    ""\n    return 1\n')))

    def test_one_file_that_fails_stops_everything_and_no_file_is_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make(Path(tmp), {**self.FILES, "cases/zz_broken.py": b"def broken(:\n"})
            before = self.snapshot(root)
            with self.assertRaises(ss.Problem) as raised:
                ss.strip_folder(root)
            self.assertIn("cases/zz_broken.py: it could not be stripped", str(raised.exception))
            self.assertEqual(self.snapshot(root), before)

    def test_the_command_says_what_it_did_or_why_it_stopped_in_plain_words_and_exits_that_way(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make(Path(tmp))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(ss.main([str(root)]), 0)
            self.assertRegex(out.getvalue(), r"^the comments and the docstrings of 3 Python files are taken out: \d+ bytes became \d+, and every line is where it was\n$")
            self.assertEqual(err.getvalue(), "")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(ss.main([str(Path(tmp) / "nowhere")]), 1)
            self.assertIn("is not a folder", err.getvalue())

    def test_a_stripper_that_changes_the_code_is_caught_by_the_check_and_stops_the_pack_with_the_files_as_they_were(self):
        mutations = {"it changes a number": (lambda text: text.replace("return 1", "return 2"), "the code changed"), "it adds a line": (lambda text: text + "\n", "the number of lines changed"),
                     "it moves a statement": (lambda text: text.replace("    return 1  # one\n", "\n    return 1"), "a statement moved to another line")}
        for name, (mutation, said) in mutations.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = self.make(Path(tmp))
                before = self.snapshot(root)
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(ss, "strip", mutation), redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(ss.main([str(root)]), 1)
                self.assertRegex(err.getvalue(), rf"^error: [a-z_/]+\.py: it could not be stripped: {said}\. The sources were not stripped and nothing is packed\.\n$")
                self.assertEqual((out.getvalue(), self.snapshot(root)), ("", before))


class TheRealApp(unittest.TestCase):
    """Every file of the cases app, stripped as the pack strips it, in a copy: function_app.py and the package cases/."""

    @classmethod
    def setUpClass(cls):
        cls.holder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.holder.cleanup)
        cls.original, cls.stripped = Path(cls.holder.name) / "original", Path(cls.holder.name) / "stripped"
        for folder in (cls.original, cls.stripped):
            (folder / "cases").mkdir(parents=True)
            for path in sorted((APP / "cases").rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    target = folder / path.relative_to(APP)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            (folder / "function_app.py").write_bytes((APP / "function_app.py").read_bytes())
        cls.count, cls.before, cls.after = ss.strip_folder(cls.stripped)
        cls.names = sorted(path.relative_to(cls.original).as_posix() for path in cls.original.rglob("*.py"))

    def test_every_file_of_the_app_is_the_same_tree_on_the_same_lines(self):
        self.assertEqual((self.count, len(self.names)), (len(self.names), len(list((APP / "cases").rglob("*.py"))) + 1))
        for name in self.names:
            before = (self.original / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
            after = (self.stripped / name).read_bytes().decode("utf-8")
            with self.subTest(name):
                self.assertEqual(without_docstrings(after), without_docstrings(before))
                self.assertEqual(after.count("\n"), before.count("\n"))
                self.assertEqual(lines_of(after), lines_of(before), "a traceback points at the same line as the file of the repository")

    def test_no_comment_and_no_text_of_a_docstring_is_left_and_the_sources_are_about_a_third_smaller(self):
        left = []
        for name in self.names:
            text = (self.stripped / name).read_text(encoding="utf-8")
            tree = ast.parse(text)
            left += [name for node in ast.walk(tree) if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node, clean=False)]
            left += [name for _ in comments_of(text)]
        self.assertEqual(left, [])
        self.assertLess(self.after, self.before * 0.75)

    def test_the_stripped_tree_compiles_and_every_module_of_it_imports_when_it_is_the_one_on_the_path(self):
        self.assertTrue(compileall.compile_dir(str(self.stripped), quiet=2, force=True), "every file compiles")
        modules = sorted(name[:-3].replace("/", ".").removesuffix(".__init__") for name in self.names if name.startswith("cases/"))
        code = ("import importlib, json, sys\nsys.path.insert(0, sys.argv[1])\nfailed, elsewhere = [], []\nfor name in json.loads(sys.argv[2]):\n    try:\n        module = importlib.import_module(name)\n"
                "        elsewhere += [name] if not module.__file__.startswith(sys.argv[1]) else []\n    except Exception as error:\n        failed.append(f'{name}: {type(error).__name__}: {error}')\nprint(json.dumps([failed, elsewhere]))\n")
        done = subprocess.run([sys.executable, "-B", "-c", code, str(self.stripped), json.dumps(modules)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [[], []], "no module fails to import, and every one is imported from the copy")
        self.assertGreater(len(modules), 50)

    def test_the_digests_that_the_lock_holds_are_the_same_when_the_app_runs_from_the_stripped_copy(self):
        lock = json.loads((APP / "cases" / "agents.lock.json").read_text(encoding="utf-8"))
        code = ("import json, sys\nsys.path.insert(0, sys.argv[1])\nfrom cases import harness, lockfile, toolbox\nassert lockfile.__file__.startswith(sys.argv[1])\n"
                "implementations, module = harness.code_digests()\nprint(json.dumps([dict(implementations), module]))\n")
        done = subprocess.run([sys.executable, "-B", "-c", code, str(self.stripped)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        implementations, module = json.loads(done.stdout)
        self.assertEqual(implementations, {name: entry["implementationSha256"] for name, entry in lock["tools"].items()}, "every tool, one digest each")
        self.assertEqual(module, lock["toolbox"]["moduleSha256"])
        self.assertGreaterEqual(len(implementations), 20, "the tools of the toolbox and the tool of the Scholar")
        for name in ("cases/toolbox.py", "cases/library.py", "cases/learning.py"):
            self.assertNotEqual((self.stripped / name).read_bytes(), (self.original / name).read_bytes(), f"{name} is stripped, so the digest is not that of the text")

    def test_the_digest_of_every_locked_module_is_the_same_for_the_original_and_for_the_stripped_file(self):
        from_repo = importlib.util.spec_from_file_location("lockfile_of_the_original", APP / "cases" / "lockfile.py")
        lockfile = importlib.util.module_from_spec(from_repo)
        sys.modules[from_repo.name] = lockfile
        from_repo.loader.exec_module(lockfile)
        for name in ("toolbox", "library", "learning"):
            original = (self.original / "cases" / f"{name}.py").read_text(encoding="utf-8")
            stripped = (self.stripped / "cases" / f"{name}.py").read_text(encoding="utf-8")
            with self.subTest(name):
                self.assertNotEqual(original, stripped)
                self.assertEqual(lockfile.source_digest(stripped), lockfile.source_digest(original))


if __name__ == "__main__":
    unittest.main()
