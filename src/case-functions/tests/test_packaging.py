import ast
import json
import re
import subprocess
import sys
import unittest

from support import APP_ROOT, REPO_ROOT

APP_FILES = ("function_app.py", "host.json", "requirements.txt")
# Words that a key, a connection string or a secret leaves behind. Nothing in the app may hold one, except the module that reads the one key
# that the gateway always requires (AGENTS.md rule 23 names it, and tools/tests/test_no_keys.py holds the exception to this one file).
FORBIDDEN = (
    "DefaultAzureCredential", "AzureNamedKeyCredential", "AzureKeyCredential", "AzureSasCredential", "ClientSecretCredential", "Credential(",
    "from_connection_string", "connection_string", "ConnectionString", "AccountKey", "SharedAccessKey", "SharedAccessSignature",
    "listKeys", "listConnectionStrings", "secondaryKey", "master_key", "sas_token", "client_secret", "password",
)
ONLY_IN_THE_GATEWAY_MODULE = ("listSecrets", "primaryKey")
GATEWAY_MODULE = "gateway.py"


def package_files():
    return sorted((APP_ROOT / "cases").glob("*.py"))


def source_files():
    """The files that are published: the entry point, the configuration and the package (no tests)."""
    return [APP_ROOT / name for name in APP_FILES] + package_files()


class FilesOfTheAppTests(unittest.TestCase):
    def test_the_source_of_the_lock_is_the_one_direct_pin_and_nothing_else(self):
        lines = (APP_ROOT / "requirements.in").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^azure-functions==[0-9][0-9A-Za-z.]*$", "an exact pin, not a range")

    def test_the_lock_pins_every_library_at_one_version_with_hashes_and_holds_the_pin(self):
        entries, current = {}, None
        for line in (APP_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            if not line.startswith(" "):
                match = re.fullmatch(r"([A-Za-z0-9._-]+)==([0-9][^\s\\;]*) \\", line)
                self.assertIsNotNone(match, f"not a pinned requirement with its hashes: {line}")
                current = match.group(1).lower()
                entries[current] = {"version": match.group(2), "hashes": 0}
            elif "--hash=" in line:
                self.assertRegex(line.strip(), r"^--hash=sha256:[0-9a-f]{64}( \\)?$")
                entries[current]["hashes"] += 1
        self.assertEqual(sorted(entries), ["azure-functions", "markupsafe", "werkzeug"], "the library and what it needs")
        for name, entry in entries.items():
            self.assertGreater(entry["hashes"], 0, f"{name} has no hash: pip would refuse the file")
        name, version = (APP_ROOT / "requirements.in").read_text(encoding="utf-8").strip().split("==")
        self.assertEqual(entries[name]["version"], version)

    def test_the_lock_is_a_subset_of_the_usage_apps_lock_for_the_same_pin(self):
        usage = (REPO_ROOT / "src" / "usage-functions" / "requirements.txt").read_text(encoding="utf-8")
        ours = (APP_ROOT / "requirements.txt").read_text(encoding="utf-8")
        for name in ("azure-functions", "markupsafe", "werkzeug"):
            block = re.search(rf"(?m)^{name}==.*?(?=^\S|\Z)", ours, re.S).group(0).split("    # via")[0]
            self.assertIn(block.strip(), usage, f"{name} has the same version and hashes as in the lock of the usage functions")

    def test_the_build_installs_only_what_the_lock_holds_and_only_when_the_hashes_match(self):
        script = (REPO_ROOT / "tools" / "build-function-app.sh").read_text(encoding="utf-8")
        self.assertIn("--require-hashes", script)
        self.assertIn('--requirement "$source_dir/requirements.txt"', script)
        self.assertIn("--only-binary=:all:", script)

    def test_host_json_keeps_every_line_of_the_history_and_the_extension_bundle(self):
        host = json.loads((APP_ROOT / "host.json").read_text(encoding="utf-8"))
        self.assertEqual(
            host,
            {
                "version": "2.0",
                "logging": {"logLevel": {"default": "Information"}, "applicationInsights": {"samplingSettings": {"isEnabled": False}}},
                "extensionBundle": {"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"},
            },
            "sampling is off, so that no line of the History is dropped",
        )
        usage = json.loads((REPO_ROOT / "src" / "usage-functions" / "host.json").read_text(encoding="utf-8"))
        self.assertEqual(host, usage)

    def test_funcignore_leaves_out_the_tests_and_compiled_files_but_not_the_libraries(self):
        lines = (APP_ROOT / ".funcignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["tests/", "__pycache__/", "*.pyc"])

    def test_the_build_finds_what_it_copies(self):
        for name in (*APP_FILES, "cases/__init__.py"):
            self.assertTrue((APP_ROOT / name).is_file(), name)

    def test_every_file_is_utf8_without_a_byte_order_mark(self):
        for path in (p for p in APP_ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and ".python_packages" not in p.parts):
            with self.subTest(file=path.relative_to(APP_ROOT).as_posix()):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                data.decode("utf-8")


class NoKeysTests(unittest.TestCase):
    def test_no_file_of_the_app_holds_a_word_that_a_key_or_a_secret_leaves_behind(self):
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            for word in FORBIDDEN:
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word.lower(), text.lower())

    def test_only_the_gateway_module_reads_the_key(self):
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            for word in ONLY_IN_THE_GATEWAY_MODULE:
                with self.subTest(file=path.name, word=word):
                    if path.name == GATEWAY_MODULE:
                        self.assertIn(word, text)
                    else:
                        self.assertNotIn(word.lower(), text.lower())

    def test_the_app_names_no_credential_class_at_all_it_asks_the_platform_for_a_token(self):
        for path in package_files():
            self.assertEqual(re.findall(r"\b\w*Credential\w*\b", path.read_text(encoding="utf-8")), [], path.name)
        self.assertIn("IDENTITY_ENDPOINT", (APP_ROOT / "cases" / "identity.py").read_text(encoding="utf-8"))


class WhatTheAppIs(unittest.TestCase):
    def test_the_package_imports_the_standard_library_only(self):
        standard = set(sys.stdlib_module_names)
        for path in package_files():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module or ""]
                for module in modules:
                    with self.subTest(file=path.name, module=module):
                        self.assertIn(module.split(".")[0], standard)

    def test_the_package_asks_questions_and_never_writes(self):
        for path in package_files():
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                for method in re.findall(r"""request\(\s*["']([A-Z]+)["']""", source):
                    self.assertIn(method, {"GET", "POST"})
                for word in ('"PUT"', '"DELETE"', '"PATCH"', "/delete", "/write", "/deallocate", "/resize", "/restart", "regeneratePrimaryKey"):
                    self.assertNotIn(word, source)

    def test_importing_the_package_loads_no_azure_module_and_makes_no_call(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import cases, cases.config, cases.http, cases.identity, cases.arm, cases.detectors, cases.evidence, cases.guards, cases.roles, cases.decide, "
            "cases.gateway, cases.events, cases.run, cases.control, cases.redact; "
            "print(sorted(name for name in sys.modules if name == 'azure' or name.startswith('azure.')))"
        )
        done = subprocess.run([sys.executable, "-c", code, str(APP_ROOT)], capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), "[]")

    def test_the_two_functions_read_and_start_nothing_but_the_watch(self):
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', (APP_ROOT / "function_app.py").read_text(encoding="utf-8"))), ["cases-control", "watch-daily"])


if __name__ == "__main__":
    unittest.main()
