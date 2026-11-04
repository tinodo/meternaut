import ast
import json
import re
import subprocess
import sys
import unittest

from support import APP_ROOT

APP_FILES = ("function_app.py", "host.json", "requirements.txt")
# Words that a key, a connection string or a secret leaves behind. Nothing in the app may hold one.
FORBIDDEN = (
    "DefaultAzureCredential", "AzureNamedKeyCredential", "AzureKeyCredential", "AzureSasCredential", "ClientSecretCredential",
    "from_connection_string", "connection_string", "ConnectionString", "AccountKey", "SharedAccessKey", "SharedAccessSignature",
    "listKeys", "listConnectionStrings", "primaryKey", "secondaryKey", "master_key", "sas_token", "client_secret", "password",
)


def source_files():
    """The files that are published: the entry point, the configuration and the usage package (no tests)."""
    files = [APP_ROOT / name for name in APP_FILES]
    files += sorted((APP_ROOT / "usage").glob("*.py"))
    return files


class FilesOfTheAppTests(unittest.TestCase):
    def test_the_requirements_are_the_four_direct_pins_and_nothing_else(self):
        lines = (APP_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["azure-functions==2.3.0", "azure-identity==1.25.3", "azure-cosmos==4.17.1", "azure-monitor-query==2.0.0"])

    def test_host_json(self):
        host = json.loads((APP_ROOT / "host.json").read_text(encoding="utf-8"))
        self.assertEqual(
            host,
            {
                "version": "2.0",
                "logging": {"logLevel": {"default": "Information"}, "applicationInsights": {"samplingSettings": {"isEnabled": False}}},
                "extensionBundle": {"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"},
            },
        )

    def test_funcignore_leaves_out_the_tests_and_compiled_files_but_not_the_libraries(self):
        lines = (APP_ROOT / ".funcignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["tests/", "__pycache__/", "*.pyc"])
        self.assertFalse([line for line in lines if "python_packages" in line])

    def test_the_build_finds_what_it_copies(self):
        for name in (*APP_FILES, "usage/__init__.py"):
            self.assertTrue((APP_ROOT / name).is_file(), name)

    def test_every_file_is_utf8_without_a_byte_order_mark(self):
        for path in (path for path in APP_ROOT.rglob("*") if path.is_file() and "__pycache__" not in path.parts and ".python_packages" not in path.parts):
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

    def test_the_only_credential_class_that_the_app_names_is_the_managed_identity(self):
        names = set()
        for path in source_files():
            names.update(re.findall(r"\b\w*Credential\b", path.read_text(encoding="utf-8")))
        self.assertEqual(names, {"ManagedIdentityCredential", "TokenCredential"})

    def test_the_credential_is_built_with_a_client_id_only(self):
        source = (APP_ROOT / "usage" / "clients.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"ManagedIdentityCredential\((.*?)\)", source), ["client_id=client_id"])


class IndexingSafetyTests(unittest.TestCase):
    def test_no_sdk_is_imported_when_the_app_is_imported(self):
        allowed = {("function_app.py", "azure.functions")}
        for path in source_files():
            if path.suffix != ".py":
                continue
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    with self.subTest(file=path.name, module=module):
                        is_azure = module == "azure" or module.startswith("azure.")
                        self.assertFalse(is_azure and (path.name, module) not in allowed)

    def test_importing_the_usage_package_loads_no_azure_module(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import usage, usage.config, usage.clients, usage.jobs, usage.events, usage.control, usage.results, usage.queries, usage.documents; "
            "print(sorted(name for name in sys.modules if name == 'azure' or name.startswith('azure.')))"
        )
        done = subprocess.run([sys.executable, "-c", code, str(APP_ROOT)], capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
