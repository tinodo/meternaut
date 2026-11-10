"""A public repository holds no secret, nothing of the owner's estate and no quoted expletive (2026-11-10, the owner: "make the project securely public").

The test reads every file that git tracks (text files up to two megabytes) and names the file and the line when it finds a private key block, a GitHub token, a storage or Service Bus key, a signed
address with its signature, a JWT that is longer than any test fixture (a real token is never shorter than 400 characters), an address at the work account domain of the owner, an expletive, or an
identifier of the owner's estate. The identifiers of the estate (the subscriptions, the tenant, the owner's object id and the identities of the project that the repository once held in a test) are kept
here as SHA-256 hashes, so that this file holds none of them: a GUID in any tracked file is hashed and looked up. The words that the test looks for are joined from pieces, so that this file does not
hold them. Whatever else is specific to the owner's estate (an internal address, a program name, the suffix of a deployed name) is not here either: it is a regular expression, one per line, in the
git-ignored file local/estate-patterns.txt (a line that starts with # is a comment; the folder can be moved with the environment variable METERNAUT_LOCAL_DIR), and that test is skipped when the file
is not there (a clone of the public repository, a runner). (The names of other projects are kept out by test_no_other_projects.py.) When a file fails, the fix is to make the line neutral: an
invented GUID, example.com, a word that is not an expletive.
"""
import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()
LOCAL_DIR = Path(os.environ.get("METERNAUT_LOCAL_DIR") or ROOT / "local")
ESTATE_PATTERNS = LOCAL_DIR / "estate-patterns.txt"
LARGEST_FILE_BYTES = 2_000_000
ESTATE_ID_HASHES = frozenset({
    "0ebe561658c973f7f020406b39144929765c7e8a33143e1a3a58cf9cf8329253",
    "120f371c6b19a1aad596295eca20acad9b2fa0fcc25adbf13f2e7e7c499f49e4",
    "3e7d06c457f345959f6541d07e88f735e276efba31de7851049e7c7c4ac7d305",
    "4046fe64095f3d46586710cac30ba2424b5b6ce2217529304ae95795e3e69c2b",
    "41caf485b1ea7b6470a5d57ade0a4a410cc4109501e83bbc7e60c9126e980256",
    "4aef866982108f62001d47032635e5726d23043e5f4b715f1ef540d386055aeb",
    "54cc35ff60500dc647317baec02de1984062ed9b1d3715c38e211dd85cb99ac6",
    "557fad916ef2e5aa296c9570f3c96c61b65a1e0182cba57e89dd3c89bdcc0b84",
    "5b43cd0d3004131929f64250a6f551476989cc5a551220240b25e20698cbc43d",
    "608fbaab8c6af79e1bddf644a9c80dea6e505a0732d8474a6f9d53410dc5186b",
    "92204270e3c8195faf2acf291f7f505b8c6b935b1cd67c2438e4e4169934e082",
    "a68196bada3ffcf85b8ed56724d62b9375aadef32b62f8ba545dac3e378e1163",
    "ba8abed4dbdba21e738235761e81956a3c98250ffa87b23c143278676a98acce",
    "d736d1f601636c472fa8b2093865a6ce70dcb83769151c7e931cd2f7e2f6448b",
    "ea3b2b110b16676cf1ee42c577edffe4b3ef3cc00c0a2f0d03116387b4347d57",
    "f6ed02b778f755436976b1125f7491cfabe02a6dff55118d3a31d794d75db556",
})
GUID = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9A-Za-z])")
EXPLETIVES = re.compile(r"(?i)\b(?:" + "fu" + r"ck\w*|" + "sh" + r"it\w*|" + "bull" + "sh" + r"it|" + "bit" + r"ch\w*|" + "ass" + r"hole\w*)\b")
RULES = {
    "a private key": re.compile("-----BEGIN [A-Z ]*" + "PRIV" + "ATE KEY-----"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}"),
    "a storage, Service Bus or Event Hubs key": re.compile(r"(?i)(?:AccountKey|SharedAccessKey|PrimaryKey|SecondaryKey)\s*=\s*[A-Za-z0-9+/]{30,}={0,2}"),
    "a signed address with its signature": re.compile(r"(?i)[?&]sig=[A-Za-z0-9%+/=]{30,}"),
    "a JWT that is no fixture": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{250,}"),
    "an address at the work account domain": re.compile(r"(?i)[A-Za-z0-9._%+-]+@(?:microsoft\.com|(?!(?:example|tenant)\.onmicrosoft)[a-z0-9-]+\.onmicrosoft\.com)\b"),
    "an expletive": EXPLETIVES,
}


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


def read_text(path: Path):
    try:
        if not path.is_file() or path.stat().st_size > LARGEST_FILE_BYTES or path.resolve() == THIS:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return None if b"\0" in data[:8192] else data.decode("utf-8", errors="replace")


class PublicHygiene(unittest.TestCase):
    def test_no_tracked_file_holds_a_secret_an_address_of_the_estate_or_an_expletive(self):
        files = tracked_files()
        if files is None:
            self.skipTest("git cannot list the tracked files here")
        self.assertGreater(len(files), 100, "the list of tracked files is the whole repository")
        found = []
        for path in files:
            text = read_text(path)
            if text is None:
                continue
            name = path.relative_to(ROOT).as_posix()
            for what, pattern in RULES.items():
                for match in pattern.finditer(text):
                    found.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}: {what}")
            for match in GUID.finditer(text):
                if hashlib.sha256(match.group(0).lower().encode()).hexdigest() in ESTATE_ID_HASHES:
                    found.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}: an identifier of the owner's estate")
        self.assertEqual(found, [], "these lines must be made neutral before the repository may stay public")

    def test_no_tracked_file_matches_the_local_estate_patterns(self):
        patterns = load_patterns(ESTATE_PATTERNS)
        if patterns is None:
            self.skipTest("local/estate-patterns.txt is not here: there is nothing of the estate to look for")
        files = tracked_files()
        if files is None:
            self.skipTest("git cannot list the tracked files here")
        found = []
        for path in files:
            text = read_text(path)
            if text is None:
                continue
            for pattern in patterns:
                for match in pattern.finditer(text):
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{text.count(chr(10), 0, match.start()) + 1}: a pattern of local/estate-patterns.txt")
        self.assertEqual(found, [], "these lines must be made neutral before the repository may stay public")

    def test_the_local_list_is_read_as_this_file_says(self):
        # A list that is read wrongly would pass for ever: a comment and a blank line are no pattern, a pattern is case-insensitive, and a missing file is None.
        with tempfile.TemporaryDirectory() as folder:
            listing = Path(folder) / "estate-patterns.txt"
            listing.write_text("# a comment\n\nacme-[0-9]+\n", encoding="utf-8")
            patterns = load_patterns(listing)
            self.assertIsNone(load_patterns(Path(folder) / "none.txt"))
        self.assertEqual(len(patterns), 1)
        self.assertTrue(patterns[0].search("the ACME-42 host"))
        self.assertFalse(patterns[0].search("acme-x"))

    def test_the_rules_find_what_they_are_made_to_find(self):
        # A rule that matches nothing would pass for ever.
        samples = {
            "a private key": "-----BEGIN " + "RSA PRIV" + "ATE KEY-----",
            "a GitHub token": "gh" + "p_" + "a" * 36,
            "a storage, Service Bus or Event Hubs key": "AccountKey=" + "A" * 40 + "==",
            "a signed address with its signature": "https://x.example/f?sv=1&sig=" + "a" * 40,
            "a JWT that is no fixture": "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 300,
            "an address at the work account domain": "someone" + "@" + "micro" + "soft.com",
            "an expletive": "what the " + "fu" + "ck",
        }
        for what, text in samples.items():
            self.assertTrue(RULES[what].search(text), what)
        for harmless in ("someone@example.onmicrosoft.com", "someone@tenant.onmicrosoft.com", "user@learn.microsoft.com", "f***ing", "S***", "10.53.0.4", "assess the hole"):
            for what, pattern in RULES.items():
                self.assertFalse(pattern.search(harmless), f"{what}: {harmless}")

    def test_the_hashes_are_of_ids_and_the_guid_pattern_finds_ids(self):
        self.assertEqual(len(ESTATE_ID_HASHES), 16)
        for digest in ESTATE_ID_HASHES:
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertTrue(GUID.search("id 5a1c0de0-0000-4000-8000-0000000000de end"))
        self.assertIsNone(GUID.search("not-a-guid-1234"))


if __name__ == "__main__":
    unittest.main()
