#!/usr/bin/env python3
"""Takes the comments and the text of the docstrings out of the Python files that the Operator receives, and keeps every line number (standard library only).

    python tools/strip-sources.py <folder>

The folder is the copy of the cases app that tools/build-function-app.sh packs for the Operator (FUNCTION_APP_SOURCES_ONLY=1). Every .py file under it is rewritten in place: a comment is cut off, with
the white space in front of it, and a docstring (the first statement of a module, a class or a function, when it is a string) becomes "" and the empty lines that its text took. No line is added or removed,
so a traceback in Application Insights points at the same line as the file of the repository. Nothing else changes: a string that is data stays as it is, and so does every line of code. About a third of
the bytes of the sources are comments and docstrings, and the request that carries the sources has a limit (docs/proposals/27-package-without-comments.md).

Every file is checked before anything is written: the syntax tree of the result has to equal the one of the original once the docstrings of both are left out, the number of lines has to be the same and every
node has to start on the same line. One file that fails stops the pack with a plain message, and no file is changed. The same text always gives the same bytes, with Python 3.12 and 3.13 alike.
tools/source-digest.py strips in memory with `stripped`, so that the digest of the files as they are shipped (PACKAGE_SHA256) can be worked out from a checkout.
"""
from __future__ import annotations

import argparse
import ast
import functools
import importlib.util
import io
import sys
import tokenize
from pathlib import Path

LOCKFILE = Path(__file__).resolve().parents[1] / "src" / "case-functions" / "cases" / "lockfile.py"


class Problem(Exception):
    """Something the caller can fix; printed without a trace."""


def _load_lockfile():
    """The one place that says what a docstring is and what the code of a file is (cases/lockfile.py, standard library only): the digests of the lock and this check stand on the same words."""
    spec = importlib.util.spec_from_file_location("lockfile_of_the_strip", LOCKFILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lockfile = _load_lockfile()


def _column(line: str, offset: int) -> int:
    """The position in characters of an offset in bytes: the syntax tree counts UTF-8 bytes and the tokenizer counts characters."""
    return len(line.encode("utf-8")[:offset].decode("utf-8"))


@functools.lru_cache(maxsize=None)
def strip(text: str) -> str:
    """The text without its comments, and with each docstring reduced to "" and the empty lines that it took. A docstring that has code after its closing quotes on the same line is left as it is."""
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise Problem("a line ends with a bare carriage return, which Python reads as a line end and this tool does not")
    lines = text.split("\n")
    for token in tokenize.generate_tokens(io.StringIO("\n".join(lines)).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            lines[row - 1] = lines[row - 1][:column].rstrip()
    for body in lockfile.docstrings(ast.parse("\n".join(lines))):
        statement = body[0]
        first, last = statement.lineno - 1, statement.end_lineno - 1
        head = lines[first][:_column(lines[first], statement.col_offset)]
        tail = lines[last][_column(lines[last], statement.end_col_offset):]
        if first != last and tail.strip():
            continue
        lines[first:last + 1] = [(head + '""' + (tail if first == last else "")).rstrip()] + [""] * (last - first)
    return "\n".join(lines)


def check(text: str, result: str) -> None:
    """Raises Problem unless the result is the text without comments and docstrings: the same number of lines, every node of the syntax tree on the same line, and the same tree."""
    text = text.replace("\r\n", "\n")
    if result.count("\n") != text.count("\n"):
        raise Problem("the number of lines changed")
    before, after = lockfile.code_tree(text), lockfile.code_tree(result)
    if [getattr(node, "lineno", 0) for node in ast.walk(before)] != [getattr(node, "lineno", 0) for node in ast.walk(after)]:
        raise Problem("a statement moved to another line")
    if lockfile.code_shape(before) != lockfile.code_shape(after):
        raise Problem("the code changed")


def stripped(data: bytes, verified: bool = True) -> bytes:
    """The bytes of a .py file as the pack ships them: LF line ends, no comments, the docstrings reduced. With `verified`, the result is checked against the original first. Raises Problem, with words
    for a person, when the file cannot be stripped."""
    try:
        text = data.decode("utf-8").replace("\r\n", "\n")
        result = strip(text)
        if verified:
            check(text, result)
    except UnicodeDecodeError:
        raise Problem("it is not UTF-8") from None
    except (SyntaxError, ValueError, tokenize.TokenError, Problem) as error:
        raise Problem(f"it could not be stripped: {error}") from None
    return result.encode("utf-8")


def strip_folder(folder: Path) -> tuple[int, int, int]:
    """Strips every .py file under the folder in place, after every one of them has passed the check. Returns the number of files, and the bytes before and after."""
    if not folder.is_dir():
        raise Problem(f"{folder} is not a folder")
    done = {}
    for path in sorted(folder.rglob("*.py")):
        data = path.read_bytes()
        try:
            done[path] = (len(data), stripped(data))
        except Problem as error:
            raise Problem(f"{path.relative_to(folder).as_posix()}: {error}") from None
    for path, (_, data) in done.items():
        path.write_bytes(data)
    return len(done), sum(before for before, _ in done.values()), sum(len(after) for _, after in done.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Takes the comments and the text of the docstrings out of the Python files under a folder, in place.")
    parser.add_argument("folder", type=Path, help="the copy of the app that is packed")
    args = parser.parse_args(argv)
    try:
        files, before, after = strip_folder(args.folder)
    except Problem as error:
        print(f"error: {error}. The sources were not stripped and nothing is packed.", file=sys.stderr)
        return 1
    print(f"the comments and the docstrings of {files} Python files are taken out: {before} bytes became {after}, and every line is where it was")
    return 0


if __name__ == "__main__":
    sys.exit(main())
