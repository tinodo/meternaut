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
KNOWN = {
    (".github/workflows/deploy-hub.yml", "listSecrets"): "the subscription key of the contract, read for one test of the gateway and masked; the way out is token validation with Microsoft Entra (an app registration)",
    (".github/workflows/deploy-hub.yml", "primaryKey"): "the same read: the field that holds the contract's key",
    ("src/case-functions/cases/gateway.py", "listSecrets"): "the first cases' app reads the contract's subscription key at the start of a run, with its own identity, a role that allows only that read, in memory and never logged; the way out is the same: token validation with Microsoft Entra",
    ("src/case-functions/cases/gateway.py", "primaryKey"): "the same read: the field that holds the contract's key",
    ("environment/gateway/logger.bicep", "instrumentationKey"): "API Management's Application Insights logger takes the instrumentation key of the component; the platform has no identity-based form of it",
}
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

    def test_the_known_ones_are_in_three_files_and_each_has_its_way_out_written_down(self):
        self.assertEqual(sorted({relative for relative, _ in KNOWN}),
                         [".github/workflows/deploy-hub.yml", "environment/gateway/logger.bicep", "src/case-functions/cases/gateway.py"])
        for reason in KNOWN.values():
            self.assertGreater(len(reason), 30)
        rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("23. **No keys, ever**", rules)
        self.assertIn("the API Management subscription key of a contract", rules)
        self.assertIn("instrumentation key that API Management's own Application Insights logger holds", rules)
        self.assertIn("the first cases' function app reads that key at the start of each run", rules)

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
