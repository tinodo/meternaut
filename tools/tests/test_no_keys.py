import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# AGENTS.md rule 23: nothing in this project authenticates with a key, a connection string, a shared access signature, an account key or a
# password. This reads everything that makes or runs the environment (the templates, the workflows, the tools, the function app) for the
# words that a key leaves behind. A word that has to stay is in KNOWN, with the reason and the way out; a word in KNOWN that is gone is an
# error too, so that the list cannot outlive what it excuses.
FORBIDDEN = {
    "listKeys": r"\blistKeys\b",
    "listConnectionStrings": r"\blistConnectionStrings\b",
    "listSecrets": r"\blistSecrets\b",
    "listAccountSas": r"\blist(Account|Service)Sas\b",
    "AccountKey": r"AccountKey",
    "SharedAccessKey": r"SharedAccessKey|SharedAccessSignature",
    "primaryKey": r"\b(primary|secondary)(Master)?Key\b",
    "instrumentationKey": r"(?i)instrumentationkey",
    "sharedKeyOn": r"allowSharedKeyAccess:\s*true",
    "localAuthOn": r"(?i)disableLocalAuth:\s*false",
    "optOut": r"SecurityControl",
    "contentShare": r"WEBSITE_CONTENTAZUREFILECONNECTIONSTRING",
    "storageConnectionString": r"DefaultEndpointsProtocol",
    "keyAuthMode": r"--auth-mode\s+key|az storage account keys",
}
KNOWN = {}
SCANNED = ("environment/**/*.bicep", "infra/**/*.bicep", ".github/workflows/*.yml", "tools/*.py", "tools/*.sh", "operator/*.sh", "src/**/*.py", "src/**/*.json", "src/**/*.txt")


def files():
    for pattern in SCANNED:
        for path in sorted(ROOT.glob(pattern)):
            relative = path.relative_to(ROOT).as_posix()
            if "/tests/" in relative or "__pycache__" in relative or ".python_packages" in relative:
                continue
            yield relative, path


def code_of(relative: str, source: str) -> str:
    """The text without its comments: a template, a workflow and a script may say in a comment what they do not do."""
    if relative.endswith(".bicep"):
        return re.sub(r"(?m)//.*$", "", source)
    if relative.endswith((".yml", ".sh")):
        return re.sub(r"(?m)^\s*#.*$|\s#\s.*$", "", source)
    if relative.endswith(".py"):
        return re.sub(r'""".*?"""', "", re.sub(r"(?m)^\s*#.*$", "", source), flags=re.S)
    return source


class NoKeys(unittest.TestCase):
    def test_nothing_that_makes_or_runs_the_environment_holds_a_key_but_what_is_known(self):
        found = set()
        for relative, path in files():
            code = code_of(relative, path.read_text(encoding="utf-8"))
            for name, pattern in FORBIDDEN.items():
                if re.search(pattern, code):
                    found.add((relative, name))
        self.assertEqual(sorted(found - set(KNOWN)), [], "a key, or the way to a key (AGENTS.md rule 23): use an identity, or say why not in KNOWN")
        self.assertEqual(sorted(set(KNOWN) - found), [], "this is no longer in the code: take it out of KNOWN")

    def test_nothing_is_known_any_more_the_app_reads_no_key_and_rule_23_says_which_exception_is_left(self):
        # The two files that held a known exception (the Hub step that read the contract's key, and the logger template that held the instrumentation key) were deleted with the objects on the
        # owner's API Management instance that they belonged to (2026-11-07): the list stays, so that a new word has to be excused here, with its reason and its way out.
        self.assertEqual(KNOWN, {})
        for gone in ("src/case-functions/cases/gateway.py", "environment/gateway", "environment/contract.json", "environment/kit-patches", "tools/gateway-prep.py", "tools/environment-smoke.py"):
            self.assertFalse((ROOT / gone).exists(), f"{gone} is gone: it read a key or made an object on the owner's API Management instance")
        rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("23. **No keys, ever**", rules)
        self.assertIn("**No other exception is left (2026-11-07):**", rules)
        self.assertIn("the connection string in the metadata of the Foundry project's tracing connection", rules)
        self.assertIn("The cases app reads no key", rules)
        self.assertIn("no Hub action reads one", rules)
        self.assertIn("holds the list of known exceptions empty", rules)
        self.assertNotIn("today that is the instrumentation key that API Management's own Application Insights logger holds", rules)
        self.assertNotIn("What remains of that key is the Hub action `contract`", rules)
        self.assertNotIn("the first cases' function app reads that key at the start of each run", rules)

    def test_the_scan_reads_what_it_is_meant_to_read(self):
        names = {relative for relative, _ in files()}
        for expected in ("environment/recording/main.bicep", "environment/cases/main.bicep", "environment/main.bicep", ".github/workflows/deploy-hub.yml", "tools/recording-check.py",
                         "tools/cases-check.py", "tools/build-function-app.sh", "operator/probe.sh", "operator/run-tool.sh", "environment/operator/main.bicep"):
            self.assertIn(expected, names)
        self.assertNotIn("tools/tests/test_no_keys.py", names)

    def test_the_patterns_find_what_they_are_for(self):
        samples = {"listKeys": "x.listKeys().keys[0]", "listConnectionStrings": "cosmos.listConnectionStrings()", "listSecrets": "/listSecrets?api", "listAccountSas": "storage.listAccountSas(x)",
                   "AccountKey": "AccountKey=abc",
                   "SharedAccessKey": "SharedAccessKeyName=x", "primaryKey": "--query primaryKey", "instrumentationKey": "instrumentationKey: x", "sharedKeyOn": "allowSharedKeyAccess: true",
                   "localAuthOn": "disableLocalAuth: false", "optOut": "SecurityControl: 'Ignore'", "contentShare": "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING: x",
                   "storageConnectionString": "DefaultEndpointsProtocol=https", "keyAuthMode": "az storage blob list --auth-mode key"}
        self.assertEqual(set(samples), set(FORBIDDEN))
        for name, sample in samples.items():
            self.assertRegex(sample, FORBIDDEN[name], name)
        for fine in ("allowSharedKeyAccess: false", "disableLocalAuth: true", "DisableLocalAuth: true", "--auth-mode login"):
            for name in ("sharedKeyOn", "localAuthOn", "keyAuthMode"):
                self.assertNotRegex(fine, FORBIDDEN[name], fine)


if __name__ == "__main__":
    unittest.main()
