"""The Hub runs in this repository, by hand, bound to the GitHub environment hub, and its log is public (AGENTS.md rules 18 and 37).

What these tests pin: the shape of the workflow (one trigger, one job bound to the environment, the permissions, a plain checkout), the split of what the job reads (every identifier of the estate is a
secret, which GitHub masks in a log and a summary, and only plain configuration is a variable), the step that masks what GitHub cannot know (the other case, the parts of a list and of the people of the console,
the digest that ends the name of every resource, the start of the addresses of a range), the steps that mask an identity or a host the moment they have read it from Azure, and that no step prints an
object id into the log or the summary of the run. No test calls GitHub or Azure."""
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ws_spec = importlib.util.spec_from_file_location("workflow_scripts_of_the_direct_hub_tests", ROOT / "tools" / "tests" / "test_workflow_scripts.py")
ws = importlib.util.module_from_spec(ws_spec)
ws_spec.loader.exec_module(ws)
lint_spec = importlib.util.spec_from_file_location("workflow_lint_of_the_direct_hub_tests", ROOT / "tools" / "workflow-lint.py")
wl = importlib.util.module_from_spec(lint_spec)
lint_spec.loader.exec_module(wl)
params_spec = importlib.util.spec_from_file_location("environment_params_of_the_direct_hub_tests", ROOT / "tools" / "environment-params.py")
ep = importlib.util.module_from_spec(params_spec)
params_spec.loader.exec_module(ep)

HUB = (ROOT / ".github" / "workflows" / "deploy-hub.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
BOOTSTRAP = (ROOT / "environment" / "BOOTSTRAP.md").read_text(encoding="utf-8").replace("\r\n", "\n")
MASKS = "Mask the identifiers of the estate in this run's log"
THE_TEAMS_ACTION = "Deploy the Teams bot"
PLAIN_CONFIGURATION = {"ENV_RESOURCE_GROUP", "ENV_LOCATION", "ENV_BUDGET_AMOUNT", "TEAMS_BOT_ENABLED"}


def code(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def steps():
    """(title, text) of every step of the job."""
    parts = re.split(r"(?m)^      - ", HUB.split("    steps:\n", 1)[1])[1:]
    return [(re.match(r"name: (.+)\n", part).group(1), part) for part in parts if part.startswith("name: ")]


def script(title):
    return ws.step_script(title)


def section(text, key, indent):
    found, inside = [], False
    for line in text.split("\n"):
        if not inside:
            inside = line == " " * indent + key + ":"
            continue
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
            break
        found.append(line)
    return "\n".join(found)


class TheShapeOfTheHub(unittest.TestCase):
    def test_it_starts_by_hand_alone_and_is_not_called(self):
        on = section(HUB, "on", 0)
        self.assertEqual(re.findall(r"(?m)^  (\w+):$", on), ["workflow_dispatch"])
        self.assertNotIn("workflow_call", code(HUB))
        self.assertNotRegex(code(HUB), r"job\.workflow|HUB_SOURCE")

    def test_the_one_job_is_bound_to_the_environment_hub_and_published_nothing(self):
        job = section(section(HUB, "jobs", 0), "hub", 2)
        self.assertEqual(re.findall(r"(?m)^    environment: (.+)$", job), ["hub"])
        self.assertIn(f"    if: {wl.OWNER_GUARD}\n", job)
        self.assertNotRegex(job, r"(?m)^    outputs:", "nothing is published as an output of the job: GitHub redacts an output that holds a secret")
        self.assertEqual(len(re.findall(r"(?m)^  [a-z][\w-]*:$", section(HUB, "jobs", 0))), 1)

    def test_the_permissions_are_a_read_of_the_repository_and_of_the_runs_and_the_token_of_the_sign_in(self):
        self.assertEqual(re.findall(r"(?m)^  ([a-z-]+): (read|write)$", section(HUB, "permissions", 0)), [("contents", "read"), ("actions", "read"), ("id-token", "write")])

    def test_the_checkout_is_the_plain_one_of_this_repository_at_the_commit_of_the_run(self):
        checkout = next(text for title, text in steps() if title == "Check out the repository")
        self.assertNotRegex(code(checkout), r"(?m)^\s*(repository|ref):")
        self.assertIn("persist-credentials: false", checkout)
        self.assertIn("uses: actions/checkout@", checkout)

    def test_a_value_that_a_dispatch_input_of_the_type_choice_takes_is_held_by_github_so_no_step_checks_it_again(self):
        self.assertNotIn("Refuse a value that the Hub does not know", HUB)
        dispatch = section(section(HUB, "on", 0), "workflow_dispatch", 2)
        for name in ("action", "evals_command", "evals_judge", "redteam_mode"):
            body = section(section(dispatch, "inputs", 4), name, 6)
            self.assertRegex(body, r"(?m)^        type: choice$", name)
            self.assertTrue(re.findall(r"(?m)^          - \S+$", body), f"{name} has options, and GitHub holds a run that is started by hand to them")
        options = re.findall(r"(?m)^          - (\S+)$", section(section(dispatch, "inputs", 4), "action", 6))
        used = set(re.findall(r"inputs\.action == '([a-z0-9-]+)'", HUB))
        self.assertEqual(sorted(used - set(options)), [], "a step that names an action that the input does not offer would never run")
        self.assertIn("what-if", options)

    def test_every_identifier_of_the_estate_is_a_secret_and_the_plain_configuration_is_a_variable(self):
        text = code(HUB)
        self.assertEqual(set(re.findall(r"\bsecrets\.([A-Za-z_]+)", text)), wl.ESTATE_SECRETS)
        self.assertEqual(set(re.findall(r"\bvars\.([A-Za-z_]+)", text)), PLAIN_CONFIGURATION)
        job_env = re.search(r"(?ms)^    env:\n(.*?)^    steps:", HUB).group(1)
        env = dict(re.findall(r"(?m)^      ([A-Z_]+): \$\{\{ (?:secrets|vars)\.([A-Za-z_]+) \}\}$", job_env))
        self.assertEqual(env["ENV_SUBSCRIPTION_ID"], "AZURE_SUBSCRIPTION_ID", "the name that the tools read is the job's, and the secret is named like the sign-in's input")
        for name in ("ENV_VNET_PREFIX", "ENV_PE_SUBNET_PREFIX", "ENV_DNS_SERVERS", "ENV_OWNER", "ENV_ALERT_EMAILS", "CONSOLE_APP_CLIENT_ID", "CONSOLE_PEOPLE", "CONSOLE_HOST_NAME", "MAIL_SENDER",
                     "DRIFT_ACCEPTED_EXEMPTIONS", "DRIFT_ACCEPTED_DENY"):
            self.assertIn(f"      {name}: ${{{{ secrets.{name} }}}}\n", job_env, name)
        for name in ("ENV_RESOURCE_GROUP", "ENV_LOCATION", "ENV_BUDGET_AMOUNT"):
            self.assertIn(f"      {name}: ${{{{ vars.{name} }}}}\n", job_env, name)
        self.assertEqual(sorted(set(PLAIN_CONFIGURATION) - {"TEAMS_BOT_ENABLED"}), sorted(name for name in env if env[name] in PLAIN_CONFIGURATION))

    def test_the_sign_in_is_azure_login_pinned_to_a_commit_with_the_three_secrets_and_nothing_else(self):
        logins = re.findall(r"uses: (azure/login@\S+) # v[\d.]+\n        with:\n          client-id: (.+)\n          tenant-id: (.+)\n          subscription-id: (.+)\n", HUB)
        self.assertGreaterEqual(len(logins), 10)
        for uses, client, tenant, subscription in logins:
            self.assertRegex(uses, r"^azure/login@[0-9a-f]{40}$")
            self.assertEqual((client, tenant, subscription), ("${{ secrets.AZURE_CLIENT_ID }}", "${{ secrets.AZURE_TENANT_ID }}", "${{ secrets.AZURE_SUBSCRIPTION_ID }}"))
        self.assertEqual(len(set(logins)), 1, "one pin everywhere")
        self.assertNotRegex(code(HUB), r"\baz login\b|client-secret|AZURE_CREDENTIALS|--password")

    def test_the_environment_folder_of_the_deploy_repository_is_gone(self):
        self.assertFalse((ROOT / "environment" / "deploy-repo").exists())
        self.assertFalse((ROOT / "tools" / "tests" / "test_deploy_repo.py").exists())

    def test_bootstrap_names_every_secret_and_every_variable_that_the_workflow_reads(self):
        for name in sorted(wl.ESTATE_SECRETS | (PLAIN_CONFIGURATION - {"TEAMS_BOT_ENABLED"})):
            self.assertIn(f"`{name}`", BOOTSTRAP, f"{name} is read by the workflow, so the page that sets the environment up has to say so")
        self.assertIn("`TEAMS_BOT_ENABLED`", BOOTSTRAP)


EXAMPLE = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555", "AZURE_TENANT_ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "AZURE_CLIENT_ID": "99999999-8888-7777-6666-555555555555",
    "ENV_RESOURCE_GROUP": "rg-example-one", "ENV_VNET_PREFIX": "10.99.0.0/24", "ENV_PE_SUBNET_PREFIX": "10.99.0.0/27", "ENV_OWNER": "Owner@Example.invalid",
    "CONSOLE_APP_CLIENT_ID": "12121212-3434-5656-7878-909090909090", "CONSOLE_HOST_NAME": "console.example.invalid", "MAIL_SENDER": "sender@example.invalid",
    "ENV_DNS_SERVERS": "10.99.1.4,10.99.1.5", "ENV_ALERT_EMAILS": "first@example.invalid, second@example.invalid",
    "DRIFT_ACCEPTED_EXEMPTIONS": "assignment-a/exemption-b, assignment-c/exemption-d", "DRIFT_ACCEPTED_DENY": "none",
    "CONSOLE_PEOPLE": '[{"oid":"abcdef12-0000-4000-8000-000000000001","name":"Ada Example","roles":["owner","approver"],"mail":"Ada@Example.invalid"},'
                      '{"oid":"abcdef12-0000-4000-8000-000000000002","name":"Bo Sample","roles":["ops"]}]',
}
NOT_IDENTIFIERS = {"ENV_LOCATION": "swedencentral", "ENV_BUDGET_AMOUNT": "25"}


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheMasks(unittest.TestCase):
    def run_masks(self, **env):
        done, _, _ = ws.run_step_script(MASKS, {}, {**{name: "" for name in EXAMPLE}, **EXAMPLE, **NOT_IDENTIFIERS, **env})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stderr, "")
        return done.stdout.splitlines()

    def masked(self, **env):
        return {line[len("::add-mask::"):] for line in self.run_masks(**env)}

    def test_it_is_the_second_step_after_the_refusal_of_the_public_gateway_which_prints_nothing_of_the_estate_and_runs_whatever_the_action_is(self):
        names = [title for title, _ in steps()]
        self.assertEqual(names[:2], ["Refuse the AI Gateway unless the owner asked for a public one in writing", MASKS])
        block = next(text for title, text in steps() if title == MASKS)
        self.assertNotIn("\n        if:", "\n" + block)
        self.assertIn("          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}\n          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}\n", block)
        self.assertNotIn("uses:", block, "it runs a shell and nothing else: no action is downloaded for it")
        self.assertNotRegex(code(block), r"\baz\b|\bgh\b|curl|\bjq\b|python")

    def test_each_identifier_is_masked_as_it_is_and_in_lower_and_upper_case_and_nothing_else_is_printed(self):
        lines = self.run_masks()
        self.assertTrue(lines and all(line.startswith("::add-mask::") for line in lines), "the step prints mask commands and no value of its own")
        masked = {line[len("::add-mask::"):] for line in lines}
        for name in ("ENV_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "ENV_VNET_PREFIX", "ENV_PE_SUBNET_PREFIX", "ENV_OWNER", "CONSOLE_APP_CLIENT_ID", "CONSOLE_HOST_NAME", "MAIL_SENDER"):
            for form in (EXAMPLE[name], EXAMPLE[name].lower(), EXAMPLE[name].upper()):
                self.assertIn(form, masked, f"{name} as {form}")

    def test_the_resource_group_the_region_and_the_budget_are_plain_configuration_and_are_left_alone(self):
        masked = self.masked()
        for left in ("rg-example-one", "RG-EXAMPLE-ONE", "swedencentral", "25"):
            self.assertNotIn(left, masked, f"{left!r} is not masked")

    def test_a_list_is_masked_whole_and_by_each_of_its_items_whatever_separates_them(self):
        masked = self.masked()
        for item in ("10.99.1.4,10.99.1.5", "10.99.1.4", "10.99.1.5", "first@example.invalid, second@example.invalid", "first@example.invalid", "second@example.invalid", "SECOND@EXAMPLE.INVALID",
                     "assignment-a/exemption-b, assignment-c/exemption-d", "assignment-a/exemption-b", "assignment-c/exemption-d"):
            self.assertIn(item, masked, item)

    def test_the_word_none_which_accepts_nothing_is_not_masked_because_it_is_no_identifier_and_would_hide_the_word_everywhere(self):
        masked = self.masked()
        for word in ("none", "NONE", "None"):
            self.assertNotIn(word, masked)
        self.assertEqual(self.masked(DRIFT_ACCEPTED_EXEMPTIONS="NONE", DRIFT_ACCEPTED_DENY="None").isdisjoint({"NONE", "None", "none"}), True)

    def test_the_people_of_the_console_are_masked_whole_and_by_their_object_id_their_name_and_their_address_and_not_by_their_roles(self):
        masked = self.masked()
        self.assertIn(EXAMPLE["CONSOLE_PEOPLE"], masked)
        for value in ("abcdef12-0000-4000-8000-000000000001", "ABCDEF12-0000-4000-8000-000000000001", "abcdef12-0000-4000-8000-000000000002", "Ada Example", "ada example", "Bo Sample",
                      "Ada@Example.invalid", "ada@example.invalid", "ADA@EXAMPLE.INVALID"):
            self.assertIn(value, masked, value)
        for left in ("owner", "approver", "ops", "oid", "name", "mail", "roles"):
            self.assertNotIn(left, masked, f"{left}: a word of the list's own shape is no identifier, and masking it would hide the word in every line of the log")

    def test_the_digest_that_ends_every_name_of_the_project_is_masked_because_it_is_worked_out_of_two_values_and_no_secret_equals_it(self):
        digest = ep.digest(EXAMPLE["ENV_SUBSCRIPTION_ID"], EXAMPLE["ENV_RESOURCE_GROUP"])
        self.assertRegex(digest, r"^[0-9a-f]{8}$")
        masked = self.masked()
        self.assertIn(digest, masked)
        self.assertIn(digest.upper(), masked)
        other = ep.digest(EXAMPLE["ENV_SUBSCRIPTION_ID"].upper(), EXAMPLE["ENV_RESOURCE_GROUP"].upper())
        self.assertEqual(other, digest, "the tool works it out in lower case, and so does this step")
        self.assertIn(ep.digest("22222222-2222-3333-4444-555555555555", "rg-two"), self.masked(ENV_SUBSCRIPTION_ID="22222222-2222-3333-4444-555555555555", ENV_RESOURCE_GROUP="rg-two"))
        self.assertIn(digest, self.masked(ENV_SUBSCRIPTION_ID=EXAMPLE["ENV_SUBSCRIPTION_ID"].upper(), ENV_RESOURCE_GROUP="RG-EXAMPLE-ONE"))
        lines = self.run_masks(ENV_SUBSCRIPTION_ID="", ENV_RESOURCE_GROUP="")
        self.assertFalse([line for line in lines if re.fullmatch(r"::add-mask::[0-9a-fA-F]{8}", line)], "no digest of nothing")

    def test_the_start_of_every_address_of_a_range_is_masked_as_far_as_whole_numbers_go(self):
        masked = self.masked()
        self.assertIn("10.99.0.", masked, "a /24 and a /27: three numbers")
        for cidr, start in (("10.99.0.0/16", "10.99."), ("10.99.4.0/22", "10.99."), ("10.99.7.0/24", "10.99.7."), ("172.20.8.32/27", "172.20.8."), ("10.99.0.0/23", "10.99.")):
            self.assertIn(start, self.masked(ENV_VNET_PREFIX=cidr, ENV_PE_SUBNET_PREFIX=""), cidr)
        for cidr in ("10.0.0.0/8", "10.99.0.0", "10.99.0.0/", "10.99.0.0/ab", "not-an-address/24", "10.99.0/24", "10.99.0.0.0/24", ""):
            lines = self.run_masks(ENV_VNET_PREFIX=cidr, ENV_PE_SUBNET_PREFIX="")
            self.assertFalse([line for line in lines if re.fullmatch(r"::add-mask::\d+\.\d+\.(\d+\.)?", line)], f"no start of a range from {cidr!r}")

    def test_a_percent_sign_and_a_line_break_in_a_value_are_written_the_way_the_runner_reads_a_command(self):
        masked = self.masked(ENV_OWNER="Owner%x@Example.invalid")
        self.assertIn("Owner%25x@Example.invalid", masked, "the runner decodes %25 to a percent sign, so the whole value is masked and not a prefix of it")
        self.assertNotIn("Owner%x@Example.invalid", masked)
        lines = self.run_masks(ENV_ALERT_EMAILS="first@example.invalid\nsecond@example.invalid")
        self.assertTrue(all(line.startswith("::add-mask::") for line in lines), "a second line of a value is never a line of the log: it would be printed unmasked")
        masked = {line[len("::add-mask::"):] for line in lines}
        for value in ("first@example.invalid%0Asecond@example.invalid", "first@example.invalid", "second@example.invalid"):
            self.assertIn(value, masked, value)

    def test_a_value_that_is_empty_or_short_is_left_alone_and_a_job_with_no_value_masks_nothing(self):
        masked = self.masked(ENV_OWNER="abc", MAIL_SENDER="", ENV_DNS_SERVERS="")
        for left in ("abc", "ABC", ""):
            self.assertNotIn(left, masked, f"{left!r} is not masked")
        self.assertNotIn("sender@example.invalid", masked)
        self.assertEqual(self.run_masks(**{name: "" for name in EXAMPLE}), [], "a job with no value masks nothing and prints nothing")


def read_sites():
    """The steps that read an identity, a client id or a host from Azure, with what each has to mask."""
    return {
        "Read the object id of the signed-in identity": ("oid",),
        "Mask the identities that exist in the project's resource group": ("id",),
        "Work out the settings": ("cases_system_principal", "operator_principal", "project_principal", "aigateway_host"),
        "Work out the settings of the AI security": ("id",),
        "Find the Operator, which runs the check from inside the network": ("client",),
        "The base and the cases app's identity are there, which the Foundry resource builds on": ("principal",),
        "Wait until the cases app answers": ("client",),
        "The cases app lists its four functions": ("system_principal",),
        "Remove the retired runner identity of the first loop, when it is still there and nothing holds it": ("principal",),
        "Knock at the web page's front door from inside the network, in the Operator": ("client",),
        "Deploy the Operator, its identity and the subnet of its container groups": ("client",),
        "Run the probe in the Operator": ("client",),
        "Find the Operator, which runs the AI Gateway check from inside the network": ("client",),
        "Read the host name of the AI Gateway from the service": ("host",),
        "The AI Gateway is there, the provider is registered, the component reports its endpoints and the gateway's identity may send to them": ("principal",),
        "Find the Operator, which runs the AI security checks from inside the network": ("client",),
        "Read the host name of the AI Gateway from the service, for the drift check": ("host",),
    }


class TheStepsThatReadAnIdentityFromAzureMaskItTheMomentTheyHaveRead(unittest.TestCase):
    def test_each_step_that_reads_an_identity_a_client_id_or_a_host_masks_it_in_a_line_that_names_the_variable(self):
        by_title = dict(steps())
        for title, variables in read_sites().items():
            self.assertIn(title, by_title, title)
            text = code(script_of(by_title[title]))
            for variable in variables:
                lines = [line for line in text.splitlines() if "::add-mask::" in line and f'"${variable}"' in line]
                self.assertTrue(lines, f"{title}: {variable} is not masked")
                self.assertTrue(all("printf" in line for line in lines), "a mask is printed by the step itself and never inside a command substitution that would swallow it")

    def test_no_step_that_reads_an_identity_from_azure_is_left_out_of_that_list_except_the_one_of_the_teams_bot_which_belongs_to_another_package(self):
        reading = re.compile(r"properties\.clientId|identity\.principalId|properties\.principalId|--output identityClientId|cases-check\.py whoami|properties\.frontend\.defaultHostname")
        listed = set(read_sites())
        found = {title for title, text in steps() if reading.search(code(text))}
        self.assertEqual(sorted(found - listed), [], "a new read of an identity or a host has to mask it, and to be listed here")
        self.assertEqual(sorted(listed - found), [], "a step of the list that reads nothing of the kind is out of date")
        teams = next(text for title, text in steps() if title == THE_TEAMS_ACTION)
        self.assertIn("--output botClientId", teams, "the Teams bot's client id is printed by the Teams action; the package that handles the bot masks it")

    def test_a_mask_is_never_swallowed_by_a_command_substitution(self):
        for title, text in steps():
            for line in code(text).splitlines():
                if "::add-mask::" in line:
                    self.assertNotRegex(line, r"\$\(.*::add-mask::", f"{title}: {line.strip()}")
                    self.assertTrue(line.lstrip().startswith(("echo ", "printf ", "[ -z")) or "printf '::add-mask::" in line, f"{title}: {line.strip()}")

    def test_the_workflow_publishes_no_object_id_in_a_line_of_the_log_or_of_a_summary(self):
        ids = ("system_principal", "cases_principal", "project_principal", "operator_principal", "cases_system_principal", "oid", "DEPLOYER_ID", "OPERATOR_CLIENT_ID", "PROJECT_PRINCIPAL", "CASES_PRINCIPAL")
        allowed = ('echo "oid=$oid" >> "$GITHUB_OUTPUT"', 'echo "foundry_project_principal=$project_principal" >> "$GITHUB_OUTPUT"', 'echo "cases_app_principal=$cases_system_principal" >> "$GITHUB_OUTPUT"')
        for title, text in steps():
            for line in code(text).splitlines():
                stripped = re.sub(r'\$\(yesno "[^"]*"\)', "", line.strip())
                if stripped in allowed or not re.match(r"(echo|printf|tee|cat)\b", stripped) or "::add-mask::" in stripped or re.match(r'echo "::(error|warning)::', stripped):
                    continue
                for variable in ids:
                    self.assertNotRegex(stripped, rf"\${{?{variable}\b", f"{title}: {stripped}")


def script_of(text):
    run = re.search(r"(?ms)^        run: \|\n(.*)", text)
    return run.group(1) if run else ""


FAKE_AZ_IDENTITIES = """#!/bin/bash
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"identity list"*) printf '%s\\t%s\\n' "$FAKE_USER_PRINCIPAL" "$FAKE_USER_CLIENT" ;;
  *"resource list"*) printf '%s\\nNone\\n%s\\n\\n' "$FAKE_APP_PRINCIPAL" "$FAKE_GATEWAY_PRINCIPAL" ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""
USER_PRINCIPAL = "aaaa0001-0000-4000-8000-000000000001"
USER_CLIENT = "aaaa0002-0000-4000-8000-000000000002"
APP_PRINCIPAL = "aaaa0003-0000-4000-8000-000000000003"
GATEWAY_PRINCIPAL = "aaaa0004-0000-4000-8000-000000000004"


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheIdentitiesOfTheProjectsGroupAreMaskedForTheWholeRun(unittest.TestCase):
    TITLE = "Mask the identities that exist in the project's resource group"

    def run_it(self, az=FAKE_AZ_IDENTITIES, **env):
        return ws.run_step_script(self.TITLE, {"az": az}, {"ENV_RESOURCE_GROUP": "rg-example", "FAKE_USER_PRINCIPAL": USER_PRINCIPAL, "FAKE_USER_CLIENT": USER_CLIENT, "FAKE_APP_PRINCIPAL": APP_PRINCIPAL,
                                                          "FAKE_GATEWAY_PRINCIPAL": GATEWAY_PRINCIPAL, **env})

    def test_every_object_id_and_client_id_that_the_group_holds_is_masked_as_it_is_and_in_upper_case_and_nothing_else_is_printed_but_a_count(self):
        done, lines, _ = self.run_it()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        masks = [line[len("::add-mask::"):] for line in done.stdout.splitlines() if line.startswith("::add-mask::")]
        for value in (USER_PRINCIPAL, USER_CLIENT, APP_PRINCIPAL, GATEWAY_PRINCIPAL):
            self.assertIn(value, masks, value)
            self.assertIn(value.upper(), masks, value)
        self.assertEqual(len(masks), 8, "None and an empty answer are no identity")
        rest = [line for line in done.stdout.splitlines() if not line.startswith("::add-mask::")]
        self.assertEqual(rest, ["Masked 4 identity ids of resource group rg-example."])
        self.assertEqual(lines, ['az identity list --resource-group rg-example --query [].[principalId, clientId] --output tsv',
                                 'az resource list --resource-group rg-example --query [].identity.principalId --output tsv'], "two reads and nothing else: it changes nothing")

    def test_a_group_with_no_identity_masks_nothing_and_says_so(self):
        quiet = "#!/bin/bash\nexit 0\n"
        done, _, _ = self.run_it(az=quiet)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), ["Masked 0 identity ids of resource group rg-example."])

    def test_a_read_that_fails_stops_the_run_because_the_log_is_public_and_an_identity_that_is_not_masked_would_be_printed(self):
        failing = "#!/bin/bash\necho 'ERROR: not allowed' >&2\nexit 1\n"
        done, _, _ = self.run_it(az=failing)
        self.assertNotEqual(done.returncode, 0)

    def test_it_runs_for_every_action_after_the_sign_in_and_the_check_of_the_group_and_before_anything_else_reads_azure(self):
        names = [title for title, _ in steps()]
        block = next(text for title, text in steps() if title == self.TITLE)
        self.assertNotIn("\n        if:", "\n" + block)
        self.assertLess(names.index("Sign in to Azure"), names.index(self.TITLE))
        self.assertEqual(names.index(self.TITLE), names.index("The resource group is there") + 1)
        self.assertLess(names.index(self.TITLE), names.index("Read the start date of the budget"))


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheObjectIdOfTheDeployIdentityIsMaskedAtOnce(unittest.TestCase):
    TITLE = "Read the object id of the signed-in identity"
    OID = "bbbb0001-0000-4000-8000-000000000001"

    def test_it_is_masked_as_it_is_and_in_upper_case_before_it_goes_to_the_output_of_the_step(self):
        python3 = f"#!/bin/bash\necho {self.OID}\n"
        done, _, out = ws.run_step_script(self.TITLE, {"python3": python3}, {})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), [f"::add-mask::{self.OID}", f"::add-mask::{self.OID.upper()}"])
        self.assertEqual(out.strip(), f"oid={self.OID}")
        self.assertNotIn(self.OID, done.stdout.replace(f"::add-mask::{self.OID}", ""))


@unittest.skipIf(ws.BASH is None, "no bash on this machine")
class TheSummaryOfTheCasesNamesNoObjectId(unittest.TestCase):
    TITLE = "The cases app lists its four functions"
    PRINCIPAL = "cccc0001-0000-4000-8000-000000000001"
    PYTHON = "#!/bin/bash\necho 'The cases app lists 6 functions:'\n"
    SITE = "/subscriptions/s/resourceGroups/g/providers/Microsoft.Web/sites/func-x"

    def run_it(self, az):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            done, _, _ = ws.run_step_script(self.TITLE, {"python3": self.PYTHON, "az": az}, {"SITE_ID": self.SITE, "GITHUB_STEP_SUMMARY": summary.as_posix()})
            return done, summary.read_text(encoding="utf-8")

    def test_an_app_that_has_an_identity_says_so_masks_its_object_id_and_prints_it_nowhere(self):
        done, text = self.run_it(f"#!/bin/bash\nprintf '%s' {self.PRINCIPAL}\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"::add-mask::{self.PRINCIPAL}", done.stdout.splitlines())
        self.assertIn(f"::add-mask::{self.PRINCIPAL.upper()}", done.stdout.splitlines())
        self.assertIn("The cases app has an identity of its own, a system-assigned one: yes.", text)
        self.assertNotIn(self.PRINCIPAL, text)
        self.assertNotIn(self.PRINCIPAL, done.stdout.replace(f"::add-mask::{self.PRINCIPAL}", ""))

    def test_an_app_that_has_none_yet_says_no_and_masks_nothing(self):
        for az in ("#!/bin/bash\nexit 1\n", "#!/bin/bash\nprintf None\n", "#!/bin/bash\nprintf ''\n"):
            done, text = self.run_it(az)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertNotIn("::add-mask::", done.stdout)
            self.assertIn("a system-assigned one: no.", text)


if __name__ == "__main__":
    unittest.main()
