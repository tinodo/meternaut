"""No tracked file names another project of the owner (AGENTS.md rule 31).

Meternaut stands alone: nothing of Meternaut names, uses, changes or depends on a project of the owner that is not part of it. The names to look for are not in this file and not in the repository:
they are regular expressions, one per line, in the git-ignored file local/other-projects.txt (a line that starts with # is a comment; the folder can be moved with the environment variable
METERNAUT_LOCAL_DIR). The test names the file and the line of every tracked file that matches one. Without that file (a clone of the public repository, a runner) there is nothing to look for and
that test is skipped; the owner's own checkout has the file. When a file fails, the line is named: rephrase it without the project, or delete the line."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = Path(os.environ.get("METERNAUT_LOCAL_DIR") or ROOT / "local")
DENY_LIST = LOCAL_DIR / "other-projects.txt"
LARGEST_FILE_BYTES = 2_000_000


def load_patterns(path: Path):
    """The compiled patterns of a deny-list (one per line, a line that starts with # is a comment), or None when the file is not there."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return [re.compile(line.strip(), re.IGNORECASE) for line in lines if line.strip() and not line.lstrip().startswith("#")]


def tracked_files():
    """The files that git tracks, or None when git cannot say (the checkout of a runner and a clone both can)."""
    try:
        done = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return [ROOT / name for name in done.stdout.decode("utf-8", errors="replace").split("\0") if name]


class NoOtherProjects(unittest.TestCase):
    def test_no_tracked_file_names_another_project_of_the_owner(self):
        patterns = load_patterns(DENY_LIST)
        if patterns is None:
            self.skipTest("local/other-projects.txt is not here: there is nothing to look for")
        files = tracked_files()
        if files is None:
            self.skipTest("git cannot list the tracked files here")
        self.assertGreater(len(files), 100, "the list of tracked files is the whole repository")
        found = []
        for path in files:
            try:
                if not path.is_file() or path.stat().st_size > LARGEST_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in patterns:
                for match in pattern.finditer(text):
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{text.count(chr(10), 0, match.start()) + 1}")
        self.assertEqual(found, [], "these lines name another project of the owner (AGENTS.md rule 31): rephrase them without it")

    def test_the_deny_list_is_read_as_this_file_says(self):
        # A list that is read wrongly would pass for ever: a comment and a blank line are no pattern, a pattern is case-insensitive, and a missing file is None (the test above is then skipped).
        with tempfile.TemporaryDirectory() as folder:
            listing = Path(folder) / "other-projects.txt"
            listing.write_text("# a comment\n\nacme[ _-]?7\n", encoding="utf-8")
            patterns = load_patterns(listing)
            self.assertIsNone(load_patterns(Path(folder) / "none.txt"))
        self.assertEqual(len(patterns), 1)
        for spelled in ("acme7", "Acme 7", "ACME-7", "acme_7", "the Acme7 platform"):
            self.assertTrue(patterns[0].search(spelled), spelled)
        self.assertFalse(patterns[0].search("acme 8"))


if __name__ == "__main__":
    unittest.main()
