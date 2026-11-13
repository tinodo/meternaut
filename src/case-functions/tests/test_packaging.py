import ast
import json
import re
import subprocess
import sys
import unittest

from support import APP_ROOT, REPO_ROOT

APP_FILES = ("function_app.py", "host.json", "requirements.txt")
# Words that a key, a connection string or a secret leaves behind. Nothing in the app may hold one: it holds no key at all (AGENTS.md rule 23), and the one key that it
# once read, the access product's key of the gateway, is gone with the gateway.
FORBIDDEN = (
    "DefaultAzureCredential", "AzureNamedKeyCredential", "AzureKeyCredential", "AzureSasCredential", "ClientSecretCredential", "Credential(",
    "from_connection_string", "connection_string", "ConnectionString", "AccountKey", "SharedAccessKey", "SharedAccessSignature",
    "listKeys", "listConnectionStrings", "secondaryKey", "master_key", "sas_token", "client_secret", "password",
)
KEY_WORDS = ("listSecrets", "primaryKey")
# The only modules that write. The store writes records to its own tables (PUT, DELETE of one entity). The families name every call that changes Azure in one module, families/calls.py (a DELETE,
# a PATCH and the deallocate of a machine, each on its own kind of resource, listed there and pinned below); the runner makes one of them, and only with the token that a person's sign-in
# to Azure gave it: no identity of the app holds a right to change Azure. The Foundry client deletes the conversations that it made itself, in Meternaut's own Foundry project and nowhere
# else (the test of its calls below holds the list, and the one DELETE of http.py's list of calls is that conversation). Everything else asks questions: a GET, or a POST that asks for
# a query result, a completion or a token. The Teams cards are one POST of a message to a private Storage queue of the loop's storage account (teamsqueue.py), on a list of calls of its own: it
# changes nothing in Azure, and it is read by a flow of Power Automate, not by this app. With TEAMS_DELIVERY=bot (teamsbot.py, on a list of calls of its own too) a card is posted to a person in Teams with a
# POST and replaced with a PUT of the Bot Connector: that changes a message in Teams and nothing in Azure (replaced by the owner's ruling of 2026-11-13 (pending his plain yes); it was the flow's alone).
WRITERS = {"store.py": {"PUT", "DELETE"}, "calls.py": {"PUT", "DELETE", "PATCH", "/deallocate"}, "foundry.py": {"DELETE"}, "http.py": {"DELETE"}, "teamsbot.py": {"PUT"}}
WRITE_WORDS = ('"PUT"', '"DELETE"', '"PATCH"', "/delete", "/write", "/deallocate", "/resize", "/restart", "regeneratePrimaryKey")


def package_files():
    """Every module of the package, the web package included."""
    return sorted(p for p in (APP_ROOT / "cases").rglob("*.py") if "__pycache__" not in p.parts)


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

    def test_the_build_installs_only_what_the_lock_holds_and_only_when_the_hashes_match(self):
        script = (REPO_ROOT / "tools" / "build-function-app.sh").read_text(encoding="utf-8")
        self.assertIn("--require-hashes", script)
        self.assertIn('--requirement "$source_dir/requirements.txt"', script)
        self.assertIn("--only-binary=:all:", script)

    def test_host_json_keeps_every_line_of_the_history_and_the_extension_bundle_and_serves_the_console_at_the_root(self):
        host = json.loads((APP_ROOT / "host.json").read_text(encoding="utf-8"))
        self.assertEqual(
            host,
            {
                "version": "2.0",
                "logging": {
                    "logLevel": {"default": "Information", "Azure.Core": "Warning", "Azure.Identity": "Warning", "Microsoft.AspNetCore": "Warning"},
                    "applicationInsights": {"samplingSettings": {"isEnabled": False}},
                },
                "extensionBundle": {"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"},
                "extensions": {"http": {"routePrefix": ""}, "queues": {"batchSize": 1, "newBatchThreshold": 0, "maxDequeueCount": 5}},
            },
            "sampling is off, so that no line of the History is dropped, and the host's own chatter is off: with the token requests of the Application Insights sign-in "
            "logged, every instance wrote about one line a second; the console's pages are at the root, with no /api in front; the control queue gives the app one message at a "
            "time (one Watch at a time, as the one partition of the old control hub did) and moves a message to cases-control-poison after five tries",
        )

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

    def test_no_module_of_the_app_reads_a_key_and_the_gateway_module_is_gone(self):
        self.assertFalse((APP_ROOT / "cases" / "gateway.py").exists())
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            for word in KEY_WORDS:
                with self.subTest(file=path.name, word=word):
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

    def test_only_the_store_the_runner_and_the_foundry_client_write_and_each_writes_only_what_it_is_for(self):
        for path in package_files():
            source = path.read_text(encoding="utf-8")
            allowed = {"GET", "POST"} | WRITERS.get(path.name, set())
            in_web = "web" in path.relative_to(APP_ROOT / "cases").parts[:-1]
            with self.subTest(file=path.relative_to(APP_ROOT).as_posix()):
                if in_web:
                    # The pages make no call at all (they ask the store and the decider), and their own routes (/me/notes/<id>/delete) are not calls.
                    self.assertNotRegex(source, r"urllib\.request|http\.client|\bsocket\b|\.request\(")
                    continue
                for method in re.findall(r"""(?:request|_call)\(\s*["']([A-Z]+)["']""", source):
                    self.assertIn(method, allowed)
                for word in WRITE_WORDS:
                    if word.strip('"') in WRITERS.get(path.name, set()):
                        continue
                    self.assertNotIn(word, source)

    def test_the_card_queue_makes_one_call_a_post_of_a_message_to_a_queue_of_the_storage_account(self):
        source = (APP_ROOT / "cases" / "teamsqueue.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"""\.request\(\s*["']([A-Z]+)["']""", source), ["POST"])
        self.assertEqual(sorted(set(re.findall(r"https://[^\"'\s]+", source))),
                         ["https://storage.azure.com/", "https://{account}.queue.core.windows.net/{queue}/messages", "https://{account}.queue.core.windows.net/{queue}/messages?messagettl={TTL_SECONDS}"],
                         "the address of the token's resource, and the one address of the one call: no other host")
        for name in ("bot", "connector", "references", "botauth", "teams"):
            self.assertFalse((APP_ROOT / "cases" / f"{name}.py").exists(), f"there is no {name}.py: the one module of a Teams client is teamsbot.py (replaced by the owner's ruling of 2026-11-13 (pending his plain yes): Meternaut has no bot in Teams)")
        self.assertFalse((APP_ROOT / "teams_function_app.py").exists())

    def test_the_store_never_talks_to_resource_manager_and_the_runner_never_to_the_table_service(self):
        store = (APP_ROOT / "cases" / "store.py").read_text(encoding="utf-8")
        runner = (APP_ROOT / "cases" / "runner.py").read_text(encoding="utf-8")
        self.assertNotIn("management.azure.com", store)
        self.assertNotIn("table.core.windows.net", runner)
        self.assertNotIn("storage.azure.com", runner)

    def test_the_families_name_eleven_writes_in_one_module_and_each_is_on_its_own_kind_of_resource(self):
        sys.path.insert(0, str(APP_ROOT))
        try:
            from cases.families import calls
        finally:
            sys.path.remove(str(APP_ROOT))
        self.assertEqual([(call.method, call.kind.collection, call.suffix) for call in calls.WRITES], [
            ("DELETE", "disks", ""), ("DELETE", "publicIPAddresses", ""), ("POST", "virtualMachines", "/deallocate"), ("PATCH", "virtualMachines", ""), ("PATCH", "disks", ""),
            ("DELETE", "snapshots", ""), ("DELETE", "networkInterfaces", ""), ("DELETE", "natGateways", ""), ("DELETE", "loadBalancers", ""), ("DELETE", "privateEndpoints", ""),
            ("PUT", "p2svpnGateways", "")])
        runner = (APP_ROOT / "cases" / "runner.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'"(?:DELETE|PATCH|PUT)"', runner), [], "the runner names no method of a write: the calls are the families'")

    def test_the_foundry_client_makes_and_deletes_only_what_is_its_own_in_its_own_project(self):
        # foundry.py is the one module that POSTs to a Foundry project and, after the store and the runner, the one that deletes. Every call goes through Foundry._call, whose
        # address is the endpoint of the one project plus one of these paths: it reads an agent, makes an agent or a version of it, makes a conversation, asks for a response,
        # and deletes the conversations that it made. The agent is never deleted. http.foundry_calls lets exactly these through, and test_foundry.py holds that list.
        source = (APP_ROOT / "cases" / "foundry.py").read_text(encoding="utf-8")
        paths: dict[str, set[str]] = {}
        for method, path in re.findall(r"""\b_call\(\s*"([A-Z]+)",\s*(f?"[^"]+")""", source):
            paths.setdefault(method, set()).add(path)
        self.assertEqual(paths, {
            # The reads of the harness and of the drift check (read_agent, list_agents) go through the same _call: the list of calls that the Watch holds (http.foundry_calls, below) lets only
            # the first through, and the drift check's client has a list of its own (cases/drift.py, tested in test_drift.py).
            "GET": {'f"/agents/{spec.name}?{API}"', 'f"/agents/{name}?{API}"', 'f"/agents?{API}&limit={LIST_PAGE}"'},
            "POST": {'f"/agents?{API}"', 'f"/agents/{spec.name}/versions?{API}"', '"/openai/v1/conversations"', '"/openai/v1/responses"'},
            "DELETE": {'f"/openai/v1/conversations/{conversation}"'},
        })
        self.assertEqual(len(re.findall(r"\.request\(", source)), 1, "every call goes through _call")
        self.assertIn('f"{self.endpoint}{path}"', source)
        self.assertEqual(set(re.findall(r"https?://[A-Za-z0-9<>.-]*[A-Za-z0-9>]", source)), {"https://ai.azure.com", "https://<account>.services.ai.azure.com"},
                         "the only addresses in the module: the resource of the token, and the shape of the endpoint in a message")
        # The list of calls (http.py) lets through the same calls and no other for a Foundry project, each on the one project's endpoint, and its one DELETE is a conversation.
        listed = (APP_ROOT / "cases" / "http.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'\("(GET|POST|DELETE)", re\.compile\(base \+ (?:rf)?("[^"]+")\)\)', listed), [
            ("GET", '"/agents/{FOUNDRY_AGENT_NAME}"'), ("POST", '"/agents"'), ("POST", '"/agents/{FOUNDRY_AGENT_NAME}/versions"'),
            ("POST", '"/openai/v1/conversations"'), ("POST", '"/openai/v1/responses"'), ("DELETE", '"/openai/v1/conversations/{FOUNDRY_CONVERSATION_ID}"')])
        self.assertEqual(listed.count('"DELETE"'), 1)

    def test_only_the_sign_in_of_a_person_starts_a_change_and_the_timer_cannot(self):
        # The change is made by `runner.execute`, with the token that the person's sign-in gave (delegated.py). The loop that the timer runs holds the list of reads only.
        importers = [path.name for path in package_files() if re.search(r"from \.runner import[^\n]*\bexecute\b", path.read_text(encoding="utf-8"))]
        self.assertEqual(importers, ["delegated.py"])
        self.assertNotIn("change_calls", (APP_ROOT / "cases" / "loop.py").read_text(encoding="utf-8"))
        self.assertIn("read_calls", (APP_ROOT / "cases" / "loop.py").read_text(encoding="utf-8"))
        users = [path.name for path in package_files() if "change_calls" in path.read_text(encoding="utf-8")]
        self.assertEqual(users, ["console.py", "delegated.py", "runner.py"], "the list is built in console.py and defined in runner.py; delegated.py names it in its text")

    def test_no_setting_names_an_identity_that_changes_azure_and_no_one_time_delay_is_left(self):
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            for word in ("WRITER_CLIENT_ID", "WRITER_RESOURCE_GROUP", "WRITER_SUBSCRIPTION_ID", "APPROVAL_DELAY_SECONDS", "id-meternaut-runner"):
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, text)

    def test_importing_the_package_loads_no_azure_module_and_makes_no_call(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import cases, cases.config, cases.http, cases.identity, cases.arm, cases.detectors, cases.evidence, cases.guards, cases.roles, cases.decide, "
            "cases.modelcalls, cases.foundry, cases.events, cases.run, cases.control, cases.redact, cases.models, cases.memory_store, cases.store, cases.approvals, cases.claims, "
            "cases.runner, cases.people, cases.switches, cases.wiring, cases.loop_config, cases.delegated, cases.console, cases.loop, cases.web, cases.mail, cases.letters, "
            "cases.agents, cases.investigate, cases.plaintext, cases.lockfile, cases.release, cases.alerts, cases.harness, cases.drift_rules, cases.drift, cases.families.registry, "
            "cases.families.words, cases.learning, cases.library, cases.study, cases.cards, cases.cardcheck, cases.offers, cases.teamsqueue, cases.teamsbot; "
            "print(sorted(name for name in sys.modules if name == 'azure' or name.startswith('azure.')))"
        )
        done = subprocess.run([sys.executable, "-c", code, str(APP_ROOT)], capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), "[]")

    def test_the_header_of_a_refused_call_is_read_by_the_runner_alone_and_is_on_no_line_of_a_log_or_of_the_history(self):
        # A claims challenge (the `www-authenticate` header of a 401) is kept on the error of the call, never in its text. The runner is the one reader, and the parser of the
        # header is in a module of its own: a second reader, or a line that logs the header or the claims in it, is a decision to make with the rules in hand.
        sources = {path: path.read_text(encoding="utf-8") for path in package_files()}
        self.assertEqual([p.name for p, text in sources.items() if re.search(r"\.challenge\b", text)], ["http.py", "runner.py"])
        self.assertEqual([p.name for p, text in sources.items() if "claims_challenge" in text], ["claims.py", "runner.py"])
        for path, text in sources.items():
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r"\b(?:emit|LOG|LOGGER|logging)\b[.(]", line):
                    with self.subTest(file=path.name, line=number):
                        self.assertNotRegex(line, r"(?i)\bclaims\b|\bchallenge\b|www-authenticate")

    def test_the_seven_functions_read_and_start_nothing_but_the_watch_the_drift_check_the_study_the_loop_and_the_card_that_the_flow_posted(self):
        self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', (APP_ROOT / "function_app.py").read_text(encoding="utf-8"))),
                         ["cards-posted", "cases-control", "console", "drift-daily", "runner-tick", "study-weekly", "watch-daily"])


if __name__ == "__main__":
    unittest.main()
