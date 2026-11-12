"""The step of the action plant that puts the planted tags back (.github/workflows/deploy-hub.yml, "Put the planted tags back on the planted disks and public IP addresses").

An outside job, which is not Meternaut's, takes the tags off the unattached test disks every night at about 22:56 UTC. The tag meternaut-planted is the first gate of every change, and that
gate is the owner's line, so a planted disk that lost its tag cannot be changed. The step puts the planted tags of environment/cases/planted.bicep back on every planted disk and public IP
address that the project's group holds. These tests run the script of the step with bash against a stand-in for az (nothing runs in Azure), and read the template, the workflow and the
planted list of the app.
"""
import importlib
import re
import sys
import unittest

from test_workflow_scripts import BASH, ROOT, WORKFLOW, run_step_script, step_script

STEP = "Put the planted tags back on the planted disks and public IP addresses"
SUBSCRIPTION = "sub-of-the-project"
GROUP = "rg-of-the-project"
OWNER = "Owner Of The Test"
LINE = "An outside job strips tags from unattached disks every night at about 22:56 UTC; approve a planted disk the same day it is planted."

# A stand-in for az: it logs each call with one unit separator after each argument (an argument can hold spaces and brackets), lists the names that the test gives for each type, and fails a tag
# update when FAKE_TAG_FAIL names a resource that ends the call.
FAKE_AZ = r"""#!/bin/bash
{ printf 'az'; for argument in "$@"; do printf '\037%s' "$argument"; done; printf '\n'; } >> "$FAKE_LOG"
case "$1 $2" in
  "resource list")
    case "$*" in
      *"--resource-type Microsoft.Compute/disks"*) if [ "$FAKE_LIST_FAIL" = disks ]; then echo "ERROR: fake az: the list of disks is refused" >&2; exit 1; fi; printf '%b' "$FAKE_DISKS" ;;
      *"--resource-type Microsoft.Network/publicIPAddresses"*) printf '%b' "$FAKE_IPS" ;;
      *) echo "unexpected type: $*" >&2; exit 9 ;;
    esac ;;
  "tag update")
    if [ -n "$FAKE_TAG_FAIL" ] && [[ "$*" == *"$FAKE_TAG_FAIL"* ]]; then echo "ERROR: fake az: the tags of this resource cannot be written" >&2; exit 1; fi ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

DISKS = "planted-disk-r7\nplanted-osdisk-r7\nplanted-disk-r12\nsomebody-elses-disk\nplanted-disk-\nplanted-disk-r7-extra\nPLANTED-disk-r7\nplanted-disk-abcdefghijklm\nplanted-vm-r7\n"
IPS = "planted-ip-r7\nplanted-ip-r12\nsomebody-elses-ip\nplanted-nic-r7\nplanted-ip-r7-extra\n"


def calls_of(lines):
    """Each logged call as its list of arguments."""
    return [line.split("\x1f")[1:] for line in lines]


def tag_updates(lines):
    return [call for call in calls_of(lines) if call[:2] == ["tag", "update"]]


@unittest.skipIf(BASH is None, "no bash on this machine")
class ThePlantedTagsArePutBack(unittest.TestCase):
    def run_step(self, disks=DISKS, ips=IPS, **env):
        return run_step_script(STEP, {"az": FAKE_AZ}, {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP, "ENV_OWNER": OWNER, "FAKE_DISKS": disks, "FAKE_IPS": ips, **env})

    def test_every_planted_disk_and_public_ip_address_of_the_group_gets_the_tags_merged_in_and_nothing_else_is_touched(self):
        done, lines, out = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        base = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers"

        def update(kind, name, planted):
            return ["tag", "update", "--resource-id", f"{base}/{kind}/{name}", "--operation", "Merge", "--tags", "workload=meternaut", "component=planted-waste", "environment=dev",
                    f"owner={OWNER}", f"meternaut-planted={planted}", "--only-show-errors", "--output", "none"]

        self.assertEqual(tag_updates(lines), [update("Microsoft.Compute/disks", "planted-disk-r7", "r7"), update("Microsoft.Compute/disks", "planted-osdisk-r7", "r7"),
                                              update("Microsoft.Compute/disks", "planted-disk-r12", "r12"), update("Microsoft.Network/publicIPAddresses", "planted-ip-r7", "r7"),
                                              update("Microsoft.Network/publicIPAddresses", "planted-ip-r12", "r12")],
                         "only the names of the planted list, each with the id of its own planting, and no resource of anybody else")
        self.assertEqual([call[:2] for call in calls_of(lines) if call[:2] != ["tag", "update"]], [["resource", "list"], ["resource", "list"]], "two lists and the updates: nothing else is called")
        for call in calls_of(lines):
            if call[:2] == ["resource", "list"]:
                self.assertEqual(call[2:4], ["--resource-group", GROUP], "the list is of the project's group alone")
        self.assertEqual(out, "", "the step has no output")

    def test_the_line_about_the_nightly_job_is_printed_once_and_in_plain_words(self):
        done, _, _ = self.run_step()
        self.assertEqual(done.stdout.splitlines().count(LINE), 1)
        self.assertIn("Planted tags put back on disks: 3.", done.stdout)
        self.assertIn("Planted tags put back on public IP addresses: 2.", done.stdout)

    def test_the_step_prints_no_id_and_no_owner_so_that_the_public_log_holds_none(self):
        done, _, _ = self.run_step()
        for secret in (SUBSCRIPTION, OWNER, "/subscriptions/"):
            self.assertNotIn(secret, done.stdout + done.stderr)

    def test_a_group_with_nothing_planted_is_a_run_that_changes_nothing_and_still_says_the_line(self):
        done, lines, _ = self.run_step(disks="", ips="")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(tag_updates(lines), [])
        self.assertIn(LINE, done.stdout)
        self.assertIn("Planted tags put back on disks: 0.", done.stdout)

    def test_a_list_that_fails_fails_the_step_and_no_tag_is_written(self):
        done, lines, _ = self.run_step(FAKE_LIST_FAIL="disks")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(tag_updates(lines), [], "a list that was refused is not an empty list")

    def test_a_tag_that_cannot_be_written_fails_the_step_at_that_resource_and_none_after_it_is_tried(self):
        done, lines, _ = self.run_step(FAKE_TAG_FAIL="planted-osdisk-r7")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual([call[3].rsplit("/", 1)[1] for call in tag_updates(lines)], ["planted-disk-r7", "planted-osdisk-r7"])

    def test_windows_line_ends_in_a_list_are_not_part_of_a_name(self):
        done, lines, _ = self.run_step(disks="planted-disk-r7\r\n", ips="")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([call[3].rsplit("/", 1)[1] for call in tag_updates(lines)], ["planted-disk-r7"])


class TheStepIsTheOneThatWasLookedAt(unittest.TestCase):
    def setUp(self):
        self.script = step_script(STEP)
        block = re.search(rf"(?ms)^      - name: {re.escape(STEP)}\n(.*?)(?=^      - |\Z)", WORKFLOW).group(1)
        self.block = block

    def test_it_is_a_step_of_the_action_plant_only_and_it_runs_after_the_planting_and_before_the_summary(self):
        self.assertIn("if: inputs.action == 'plant'", self.block)
        names = re.findall(r"(?m)^      - name: (.+)$", WORKFLOW)
        self.assertEqual(names.index(STEP), names.index("Plant the waste") + 1)
        self.assertEqual(names[names.index(STEP) + 1], "What was planted", "the table of what was planted shows the tags that were put back")

    def test_it_changes_tags_with_a_merge_and_with_no_other_kind_of_call(self):
        code = "\n".join(line for line in self.script.splitlines() if not line.lstrip().startswith("#"))
        self.assertEqual(re.findall(r"\baz [a-z]+ [a-z]+", code), ["az resource list", "az tag update"])
        self.assertIn("--operation Merge", code)
        for word in ("--operation Replace", "--operation Delete", "az resource delete", "az resource tag", "--method", "GITHUB_OUTPUT", "::add-mask::", "az login"):
            self.assertNotIn(word, code)
        self.assertNotIn("${{", self.script, "no expression inside a script: a value reaches it through the environment of the job")

    def test_the_id_is_built_from_the_subscription_and_the_group_of_the_project_and_nothing_else(self):
        self.assertIn('--resource-id "/subscriptions/$ENV_SUBSCRIPTION_ID/resourceGroups/$ENV_RESOURCE_GROUP/providers/$type/$name"', self.script)
        for call in re.findall(r"az resource list[^\n]*", self.script):
            self.assertIn('--resource-group "$ENV_RESOURCE_GROUP"', call)

    def test_the_tags_are_the_tags_of_the_template_and_so_is_their_value(self):
        template = (ROOT / "environment" / "cases" / "planted.bicep").read_text(encoding="utf-8")
        body = re.search(r"var tags = \{(.*?)\n\}", template, re.S).group(1)
        in_template = dict(re.findall(r"^\s*'?([\w-]+)'?: (.+)$", body, re.M))
        self.assertEqual(in_template, {"workload": "'meternaut'", "component": "'planted-waste'", "environment": "'dev'", "owner": "owner", "meternaut-planted": "plantedId"})
        wanted = re.search(r'--tags ((?:"[^"]+" ?)+) --only-show-errors', self.script).group(1)
        in_step = dict(item.split("=", 1) for item in re.findall(r'"([^"]+)"', wanted))
        self.assertEqual(in_step, {"workload": "meternaut", "component": "planted-waste", "environment": "dev", "owner": "$ENV_OWNER", "meternaut-planted": "${name##*-}"},
                         "the same keys, the same fixed values, the owner of the run and the id that the name of the resource carries")

    def test_the_names_that_it_acts_on_are_never_wider_than_the_planted_list_of_the_app_and_take_every_name_that_the_template_makes(self):
        sys.path.insert(0, str(ROOT / "src" / "case-functions"))
        try:
            gates = importlib.import_module("cases.families.gates")
        finally:
            sys.path.pop(0)
        patterns = dict(re.findall(r"""put_back "(Microsoft\.[\w/]+)" '(\^[^']+\$)' """, self.script))
        self.assertEqual(list(patterns), ["Microsoft.Compute/disks", "Microsoft.Network/publicIPAddresses"])
        candidates = ("planted-disk-r42", "planted-osdisk-r42", "planted-ip-r42", "planted-vm-r42", "planted-nic-r42", "planted-disk-", "planted-xx-r42", "planted-disk-r42-extra", "disk-r42",
                      "planted-disk-" + "x" * 12, "planted-disk-" + "x" * 13, "planted-ip-" + "x" * 13, "")
        for kind, pattern in patterns.items():
            for name in candidates:
                if re.fullmatch(pattern, name):
                    self.assertTrue(gates.on_planted_list(kind, name), f"{kind} {name!r}: the step acts on a name that the planted list of the app does not accept")
        made = {"Microsoft.Compute/disks": ("planted-disk-r42", "planted-osdisk-r42", "planted-disk-" + "x" * 12), "Microsoft.Network/publicIPAddresses": ("planted-ip-r42", "planted-ip-a")}
        for kind, names in made.items():
            for name in names:
                self.assertIsNotNone(re.fullmatch(patterns[kind], name), f"{kind} {name!r} is made by the template and the step does not take it")
        for kind, pattern in patterns.items():
            for other in ("planted-vm-r42", "planted-nic-r42", "planted-disk-", "planted-disk-" + "x" * 13, "planted-ip-" + "x" * 13, "somebody-elses-disk", ""):
                self.assertIsNone(re.fullmatch(pattern, other), f"{kind} {other!r}")

    def test_the_step_does_not_touch_machines_or_network_interfaces_because_the_outside_job_only_strips_unattached_disks_and_a_machine_is_not_one(self):
        code = "\n".join(line for line in self.script.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("virtualMachines", code)
        self.assertNotIn("networkInterfaces", code)

    def test_the_input_and_the_summary_say_that_the_tags_are_put_back_and_why(self):
        description = re.search(r'(?m)^        description: "(what-if: .+)"$', WORKFLOW).group(1)
        plant = description.split(" plant: ")[1].split(" loop-check: ")[0]
        self.assertIn("It also puts the planted tags back on every planted disk and public IP address that the group already holds, because an outside job strips the tags from unattached disks every "
                      "night at about 22:56 UTC", plant)
        for line in re.findall(r'(?m)^\s+plant\) echo "(.*?)" ;;$', WORKFLOW):
            self.assertTrue("puts the planted tags back" in line or "planted tags were put back" in line, line)
        self.assertEqual(len(re.findall(r'(?m)^\s+plant\) echo ', WORKFLOW)), 2, "a line for a run that failed and one for a run that finished")


if __name__ == "__main__":
    unittest.main()
