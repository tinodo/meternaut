"""The Hub can be called by the workflow of a private deploy repository (environment/deploy-repo/README.md), and the first steps of its job hold that call to what it says.

What these tests pin: the call has the same inputs and the three secrets that the job reads, the first steps mask the identifiers of the estate and refuse a value that the Hub does not know, and the template of the
caller passes everything by name, pins a commit through a placeholder that is not one, and holds no more than the Hub needs. No test calls GitHub or Azure."""
import re
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workflow_scripts_of_the_deploy_repository_tests", ROOT / "tools" / "tests" / "test_workflow_scripts.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)
lint_spec = importlib.util.spec_from_file_location("workflow_lint_of_the_deploy_repository_tests", ROOT / "tools" / "workflow-lint.py")
wl = importlib.util.module_from_spec(lint_spec)
lint_spec.loader.exec_module(wl)

HUB = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
TEMPLATE = (ROOT / "environment" / "deploy-repo" / "hub.yml.template").read_text(encoding="utf-8").replace("\r\n", "\n")
README = (ROOT / "environment" / "deploy-repo" / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
MASKS = "Mask the identifiers of the estate in this run's log"
VALUES = "Refuse a value that the Hub does not know"
PLACEHOLDER = "<FULL-40-CHARACTER-COMMIT-OF-THE-PUBLIC-REPOSITORY>"
THE_HUBS_OWN_GROUP = "hub"


def section(text, key, indent):
    """The lines under `key:` at this indentation, up to the next line that is not indented deeper (comments do not end it)."""
    found, inside = [], False
    for line in text.split("\n"):
        if not inside:
            inside = line == " " * indent + key + ":"
            continue
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
            break
        found.append(line)
    return "\n".join(found)


def inputs_of(block):
    """The inputs of a trigger, in order, each as {type, default, required, options}."""
    inputs = section(block, "inputs", 4)
    found = {}
    for name in re.findall(r"(?m)^      (\w+):$", inputs):
        body = section(inputs, name, 6)
        found[name] = {"type": (re.search(r"(?m)^        type: (\w+)$", body) or [None, None])[1], "default": (re.search(r"(?m)^        default: (.+)$", body) or [None, None])[1],
                       "required": (re.search(r"(?m)^        required: (\w+)$", body) or [None, None])[1], "options": re.findall(r"(?m)^          - (\S+)$", body)}
    return found


ON = section(HUB, "on", 0)
DISPATCH = inputs_of(section(ON, "workflow_dispatch", 2))
CALL = inputs_of(section(ON, "workflow_call", 2))


def script_of(name):
    return ws.step_script(name)


def names_of(text):
    return [re.match(r"name: (.+)\n", block).group(1) for block in re.split(r"(?m)^      - ", text.split("    steps:\n", 1)[1])[1:]]


def code(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class TheCall(unittest.TestCase):
    def test_the_hub_starts_by_hand_and_by_a_call_and_the_call_has_the_same_inputs_with_the_same_defaults(self):
        self.assertEqual(re.findall(r"(?m)^  (\w+):$", ON), ["workflow_dispatch", "workflow_call"])
        self.assertEqual(list(CALL), list(DISPATCH), "an input that the called workflow does not declare is an error, and one that it declares and the caller never passes is ignored")
        for name, wanted in DISPATCH.items():
            with self.subTest(name):
                # a call has no type choice: the options become strings, which the first steps of the job check
                self.assertEqual(CALL[name]["type"], "string" if wanted["type"] == "choice" else wanted["type"])
                # a call that leaves the action out is refused at its start instead of falling back to a default: the action is what the owner means to run
                self.assertEqual(CALL[name]["default"], None if name == "action" else wanted["default"])
                self.assertEqual(CALL[name]["required"], wanted["required"])
                self.assertEqual(CALL[name]["options"], [], "workflow_call has no options")

    def test_the_call_declares_the_three_secrets_that_the_job_reads_and_nothing_else_of_the_callers_secrets_is_read(self):
        read = set(re.findall(r"\bsecrets\.([A-Za-z_]+)", code(HUB))) - {"GITHUB_TOKEN"}
        declared = section(section(ON, "workflow_call", 2), "secrets", 4)
        self.assertEqual(read, {"AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"})
        self.assertEqual(set(re.findall(r"(?m)^      (\w+):$", declared)), read)
        for name in read:
            self.assertRegex(section(declared, name, 6), r"(?m)^        required: true$", f"{name}: a call without it stops at the start of the run and says so")

    def test_the_variables_that_the_job_reads_are_the_callers_and_the_readme_of_the_deploy_repository_names_every_one(self):
        read = set(re.findall(r"\bvars\.([A-Z_]+)", code(HUB)))
        self.assertGreaterEqual(len(read), 15)
        for name in sorted(read):
            self.assertIn(f"`{name}`", README, f"{name} is read from the variables of the caller's repository, so the page that sets that repository up has to say so")

    def test_every_action_that_the_input_offers_is_known_to_the_check_of_the_values_and_no_other(self):
        script = script_of(VALUES)
        for variable, name in (("ACTION", "action"), ("EVALS_COMMAND", "evals_command"), ("EVALS_JUDGE", "evals_judge"), ("REDTEAM_MODE", "redteam_mode")):
            options = re.search(rf'(?m)^case "\${variable}" in\n\s+(.+?)\) ;;$', script)
            self.assertIsNotNone(options, variable)
            self.assertEqual(options.group(1).split(" | "), DISPATCH[name]["options"], f"the list of the check and the options of the input {name} are one list")

    def test_the_hub_reads_the_commit_and_the_repository_of_its_code_from_the_job_context_and_the_run_number_stays_the_callers(self):
        self.assertIn("      PLANTED_ID: r${{ github.run_number }}\n", HUB, "the number of a run is the caller's and unique there: it names what a run plants")
        self.assertEqual(len(re.findall(r"HUB_SOURCE_SHA: \$\{\{ job\.workflow_sha \}\}", HUB)), 3, "the check of CI, the release of the app and the drift check")
        self.assertEqual(len(re.findall(r"HUB_SOURCE_REPOSITORY: \$\{\{ job\.workflow_repository \}\}", HUB)), 1)
        self.assertNotRegex(re.search(r"(?ms)^    env:\n(.*?)^    steps:", HUB).group(1), r"job\.", "the job context does not exist in the env of a job, only in a step")


EXAMPLE = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "AZURE_TENANT_ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "AZURE_CLIENT_ID": "99999999-8888-7777-6666-555555555555",
    "ENV_RESOURCE_GROUP": "rg-example-one", "ENV_VNET_PREFIX": "10.99.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.99.0.0/27", "ENV_OWNER": "Owner@Example.invalid",
    "CONSOLE_APP_CLIENT_ID": "12121212-3434-5656-7878-909090909090", "CONSOLE_HOST_NAME": "console.example.invalid", "MAIL_SENDER": "sender@example.invalid",
    "ENV_DNS_SERVERS": "10.99.1.4,10.99.1.5", "ENV_ALERT_EMAILS": "first@example.invalid, second@example.invalid", "CONSOLE_PEOPLE": "id-one id-two,id-three",
}
NOT_IDENTIFIERS = {"ENV_LOCATION": "swedencentral", "ENV_BUDGET_AMOUNT": "25"}


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheMasks(unittest.TestCase):
    def run_masks(self, **env):
        done, _, _ = ws.run_step_script(MASKS, {}, {**{name: "" for name in EXAMPLE}, **EXAMPLE, **NOT_IDENTIFIERS, **env})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stderr, "")
        return done.stdout.splitlines()

    def test_it_is_the_second_step_after_the_refusal_of_the_public_gateway_which_prints_nothing_of_the_estate_and_runs_whatever_the_action_is(self):
        names = names_of(HUB)
        self.assertEqual(names[:2], ["Refuse the AI Gateway unless the owner asked for a public one in writing", MASKS])
        block = re.search(rf"(?ms)^      - name: {re.escape(MASKS)}\n(.*?)(?=^      - )", HUB).group(1)
        self.assertNotIn("\n        if:", "\n" + block)
        self.assertIn("          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}\n          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}\n", block)
        self.assertNotIn("uses:", block, "it runs a shell and nothing else: no action is downloaded for it")

    def test_each_identifier_is_masked_as_it_is_and_in_lower_and_upper_case_and_nothing_else_is_printed(self):
        lines = self.run_masks()
        self.assertTrue(lines and all(line.startswith("::add-mask::") for line in lines), "the step prints mask commands and no value of its own")
        masked = {line[len("::add-mask::"):] for line in lines}
        for name in ("ENV_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "ENV_RESOURCE_GROUP", "ENV_VNET_PREFIX", "ENV_PE_SUBNET_PREFIX", "ENV_OWNER", "CONSOLE_APP_CLIENT_ID", "CONSOLE_HOST_NAME", "MAIL_SENDER"):
            for form in (EXAMPLE[name], EXAMPLE[name].lower(), EXAMPLE[name].upper()):
                self.assertIn(form, masked, f"{name} as {form}")
        for value in ("Owner@Example.invalid", "owner@example.invalid", "OWNER@EXAMPLE.INVALID"):
            self.assertIn(value, masked)

    def test_a_list_is_masked_whole_and_by_each_of_its_items_whatever_separates_them(self):
        masked = {line[len("::add-mask::"):] for line in self.run_masks()}
        for item in ("10.99.1.4,10.99.1.5", "10.99.1.4", "10.99.1.5", "first@example.invalid, second@example.invalid", "first@example.invalid", "second@example.invalid", "SECOND@EXAMPLE.INVALID",
                     "id-one id-two,id-three", "id-one", "id-two", "id-three"):
            self.assertIn(item, masked, item)

    def test_the_region_and_the_budget_are_not_identifiers_and_a_value_that_is_empty_or_short_is_left_alone(self):
        lines = self.run_masks(ENV_OWNER="abc", MAIL_SENDER="", ENV_DNS_SERVERS="")
        masked = {line[len("::add-mask::"):] for line in lines}
        for left in ("swedencentral", "25", "abc", "ABC", ""):
            self.assertNotIn(left, masked, f"{left!r} is not masked")
        self.assertNotIn("sender@example.invalid", masked)
        self.assertEqual(self.run_masks(**{name: "" for name in EXAMPLE}), [], "a job with no value masks nothing and prints nothing")

    def test_a_percent_sign_in_a_value_is_written_the_way_the_runner_reads_a_command(self):
        masked = {line[len("::add-mask::"):] for line in self.run_masks(ENV_RESOURCE_GROUP="rg%x-1234")}
        self.assertIn("rg%25x-1234", masked, "the runner decodes %25 to a percent sign, so the whole value is masked and not a prefix of it")
        self.assertNotIn("rg%x-1234", masked)


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheCheckOfTheValues(unittest.TestCase):
    GOOD = {"ACTION": "what-if", "EVALS_COMMAND": "probe", "EVALS_JUDGE": "none", "REDTEAM_MODE": "auto"}

    def run_values(self, **env):
        done, _, _ = ws.run_step_script(VALUES, {}, {**self.GOOD, **env})
        return done

    def test_the_defaults_and_every_option_of_every_input_pass(self):
        self.assertEqual(self.run_values().returncode, 0)
        for variable, name in (("ACTION", "action"), ("EVALS_COMMAND", "evals_command"), ("EVALS_JUDGE", "evals_judge"), ("REDTEAM_MODE", "redteam_mode")):
            for option in DISPATCH[name]["options"]:
                with self.subTest(name=name, option=option):
                    done = self.run_values(**{variable: option})
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_value_that_the_hub_does_not_know_stops_the_run_before_anything_else_and_is_not_printed(self):
        for variable, name in (("ACTION", "action"), ("EVALS_COMMAND", "evals_command"), ("EVALS_JUDGE", "evals_judge"), ("REDTEAM_MODE", "redteam_mode")):
            for value in ("", "unknown", "What-If", "what-if ", "what-if\n::warning::x", "cases;rm", "--all", "deploy"):
                with self.subTest(name=name, value=value):
                    done = self.run_values(**{variable: value})
                    self.assertEqual(done.returncode, 1)
                    text = done.stdout + done.stderr
                    self.assertIn(f"for the input {name}.", text)
                    self.assertIn("Nothing was changed.", text)
                    self.assertNotIn("::warning::x", text, "what the caller sent is never echoed into the log, where a workflow command in it would be read")

    def test_it_is_the_third_step_and_asks_nothing_of_github_or_azure(self):
        self.assertEqual(names_of(HUB)[2], VALUES)
        self.assertNotRegex(code(script_of(VALUES)), r"\baz\b|\bgh\b|curl|checkout")


class TheTemplateOfTheCaller(unittest.TestCase):
    JOB = section(section(TEMPLATE, "jobs", 0), "hub", 2)

    def test_it_starts_by_hand_alone_with_the_inputs_of_the_hub_and_passes_each_by_name(self):
        triggers = section(TEMPLATE, "on", 0)
        self.assertEqual(re.findall(r"(?m)^  (\w+):$", triggers), ["workflow_dispatch"])
        inputs = inputs_of(section(triggers, "workflow_dispatch", 2))
        self.assertEqual(list(inputs), list(DISPATCH))
        for name, wanted in DISPATCH.items():
            with self.subTest(name):
                self.assertEqual(inputs[name], wanted, "the same type, default, requirement and options as the Hub's own input")
        passed = re.findall(r"(?m)^      (\w+): \$\{\{ inputs\.(\w+) \}\}$", section(self.JOB, "with", 4))
        self.assertEqual(passed, [(name, name) for name in DISPATCH], "each input goes through under its own name")

    def test_it_pins_the_hub_to_a_placeholder_that_is_not_a_commit_so_that_nobody_runs_it_by_accident_and_a_commit_makes_it_valid(self):
        (uses,) = re.findall(r"(?m)^    uses: (\S+)$", self.JOB)
        self.assertEqual(uses, f"tinodo/meternaut/.github/workflows/deploy-hub.yml@{PLACEHOLDER}")
        self.assertIsNone(wl.PINNED.match(uses), "the placeholder is not a pin: the lint of the deploy repository, and GitHub, refuse it until it is replaced")
        self.assertIsNotNone(wl.PINNED.match(uses.replace(PLACEHOLDER, "0123456789abcdef0123456789abcdef01234567")))
        self.assertNotRegex(code(TEMPLATE), r"uses:.*\$\{\{", "uses: cannot hold an expression")

    def test_it_holds_the_guard_the_three_permissions_and_the_three_secrets_by_name_and_nothing_else(self):
        self.assertIn(f"    if: {wl.OWNER_GUARD}\n", self.JOB)
        permissions = section(self.JOB, "permissions", 4)
        self.assertEqual(re.findall(r"(?m)^      ([a-z-]+): (\w+)$", permissions), [("contents", "read"), ("actions", "read"), ("id-token", "write")])
        self.assertRegex(TEMPLATE, r"(?m)^permissions:\n  contents: read\n(?!  )", "nothing is held at the top of the workflow but a read")
        secrets = section(self.JOB, "secrets", 4)
        self.assertEqual(re.findall(r"(?m)^      (\w+): \$\{\{ secrets\.(\w+) \}\}$", secrets), [(n, n) for n in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID")])
        self.assertNotIn("inherit", code(TEMPLATE))
        for forbidden in ("pull_request", "workflow_run", "issue_comment", "schedule", "runs-on", "self-hosted", "continue-on-error", "steps:"):
            self.assertNotIn(forbidden, code(TEMPLATE), forbidden)

    def test_the_secrets_it_passes_are_the_ones_that_the_hub_declares_and_the_group_of_the_call_is_not_the_hubs_own(self):
        declared = set(re.findall(r"(?m)^      (\w+):$", section(section(ON, "workflow_call", 2), "secrets", 4)))
        self.assertEqual(declared, set(re.findall(r"(?m)^      (\w+): \$\{\{ secrets\.", section(self.JOB, "secrets", 4))))
        concurrency = section(self.JOB, "concurrency", 4)
        self.assertNotEqual(re.search(r"(?m)^      group: (\S+)$", concurrency).group(1), THE_HUBS_OWN_GROUP)
        self.assertRegex(HUB, rf"(?m)^concurrency:\n  group: {THE_HUBS_OWN_GROUP}\n")
        self.assertIn("      cancel-in-progress: false", concurrency, "a second run waits and is never cancelled")


class TheReadmeOfTheDeployRepository(unittest.TestCase):
    def test_it_names_the_pin_of_the_sign_in_that_the_hub_uses_and_the_three_secrets(self):
        login = re.search(r"uses: (azure/login@[0-9a-f]{40})", HUB).group(1)
        self.assertIn(login, README, "the allow list of the deploy repository has to name the commit that the Hub pins")
        for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "hub.yml.template", "what-if"):
            self.assertIn(name, README, name)

    def test_the_things_it_says_are_not_verified_are_said_and_nothing_in_it_claims_that_it_has_run(self):
        for words in ("Not verified, and why it costs nothing", "disabled in its own repository", "Nothing in this folder has run", "A part is done when it has run"):
            self.assertIn(words, README, words)
        for claim in ("has run in Azure", "ran in Azure", "was deployed", "has been deployed"):
            self.assertNotIn(claim, README, claim)

    def test_every_link_to_a_file_of_the_repository_resolves(self):
        for target in re.findall(r"\]\((\.\.?/[^)#]+)", README):
            self.assertTrue((ROOT / "environment" / "deploy-repo" / target).resolve().exists(), target)

    def test_the_pages_that_describe_how_the_hub_runs_point_at_it(self):
        for path, link in (("environment/BOOTSTRAP.md", "(deploy-repo/README.md)"), ("docs/proposals/16-the-hub-on-the-owners-machine.md", "(../../environment/deploy-repo/README.md)")):
            self.assertIn(link, (ROOT / path).read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main()
