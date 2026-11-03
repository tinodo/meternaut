import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "hub-params.py"
spec = importlib.util.spec_from_file_location("hub_params", TOOL)
hp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hp)

BICEP = (Path(__file__).resolve().parents[2] / "hub" / "main.bicep").read_text(encoding="utf-8")
ENV = {
    "HUB_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555",
    "HUB_RESOURCE_GROUP": "rg-meternaut-hub",
    "HUB_LOCATION": "swedencentral",
    "HUB_VNET_PREFIX": "10.52.0.0/27",
    "HUB_PE_SUBNET_PREFIX": "10.52.0.0/28",
    "HUB_DNS_SERVERS": "10.20.0.4",
    "HUB_OWNER": "owner@example.com",
    "HUB_BUDGET_AMOUNT": "20",
    "HUB_ALERT_EMAILS": "owner@example.com",
    "HUB_APIM_PRINCIPAL_ID": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
}


def run(env):
    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "parameters.json"
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = hp.main(["--out", str(out_file)], environ=env)
        document = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else None
    return code, out.getvalue(), err.getvalue(), document


def bicep_params():
    declared = {}
    for match in re.finditer(r"^param (\w+) (\w+)( = .+)?$", BICEP, re.M):
        declared[match.group(1)] = (match.group(2), match.group(3) is not None)
    return declared


class Build(unittest.TestCase):
    def test_a_good_set_of_settings_gives_the_parameter_file_and_the_outputs(self):
        code, out, err, document = run(ENV)
        self.assertEqual((code, err), (0, ""))
        values = {k: v["value"] for k, v in document["parameters"].items()}
        self.assertEqual(values["location"], "swedencentral")
        self.assertEqual(values["vnetAddressPrefix"], "10.52.0.0/27")
        self.assertEqual(values["peSubnetPrefix"], "10.52.0.0/28")
        self.assertEqual(values["dnsServers"], ["10.20.0.4"])
        self.assertEqual(values["alertEmails"], ["owner@example.com"])
        self.assertEqual(values["budgetAmount"], 20)
        self.assertEqual(values["apimPrincipalId"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(document["contentVersion"], "1.0.0.0")
        lines = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(lines["account_name"], values["accountName"])
        self.assertEqual(lines["private_endpoint"], "pe-" + values["accountName"])
        self.assertEqual(lines["endpoint"], f"https://{values['accountName']}.cognitiveservices.azure.com")

    def test_the_account_name_is_a_valid_host_name_and_the_same_on_every_run(self):
        names = {run(ENV)[3]["parameters"]["accountName"]["value"] for _ in range(3)}
        self.assertEqual(len(names), 1)
        name = names.pop()
        self.assertRegex(name, r"^aif-meternaut-[0-9a-f]{8}$")
        self.assertTrue(2 <= len(name) <= 64)

    def test_the_name_differs_per_subscription_and_group_and_ignores_case(self):
        base = hp.account_name(ENV["HUB_SUBSCRIPTION_ID"], "rg-a")
        self.assertNotEqual(base, hp.account_name(ENV["HUB_SUBSCRIPTION_ID"], "rg-b"))
        self.assertNotEqual(base, hp.account_name("99999999-2222-3333-4444-555555555555", "rg-a"))
        self.assertEqual(base, hp.account_name(ENV["HUB_SUBSCRIPTION_ID"].upper(), "RG-A"))

    def test_the_file_matches_the_parameters_of_the_template(self):
        declared = bicep_params()
        given = set(run(ENV)[3]["parameters"])
        self.assertTrue(given <= set(declared), given - set(declared))
        required = {name for name, (_, has_default) in declared.items() if not has_default}
        self.assertTrue(required <= given, required - given)
        types = {"string": str, "int": int, "array": list, "bool": bool}
        for name, wrapped in run(ENV)[3]["parameters"].items():
            self.assertIsInstance(wrapped["value"], types[declared[name][0]], name)

    def test_the_private_endpoint_has_the_name_the_workflow_waits_for(self):
        self.assertIn("name: 'pe-${accountName}'", BICEP)

    def test_the_other_names_the_workflow_removes_are_the_ones_the_template_gives(self):
        lines = dict(line.split("=", 1) for line in run(ENV)[1].splitlines())
        self.assertIn("param workload string = 'meternaut'", BICEP)
        self.assertIn("name: 'vnet-${workload}'", BICEP)
        self.assertIn("name: 'nsg-${workload}-pe'", BICEP)
        self.assertEqual(lines["vnet_name"], "vnet-meternaut")
        self.assertEqual(lines["nsg_name"], "nsg-meternaut-pe")

    def test_the_restore_switch_is_a_template_parameter_the_file_leaves_alone(self):
        self.assertEqual(bicep_params()["restoreAccount"], ("bool", True))
        self.assertNotIn("restoreAccount", run(ENV)[3]["parameters"])


class Refusals(unittest.TestCase):
    def refused(self, **changes):
        env = {**ENV, **changes}
        code, out, err, document = run(env)
        self.assertEqual(code, 2, changes)
        self.assertIsNone(document, "nothing is written for a bad setting")
        self.assertEqual(out, "")
        return err

    def test_a_missing_setting_is_named(self):
        for name in ENV:
            env = {k: v for k, v in ENV.items() if k != name}
            code, _, err, _ = run(env)
            self.assertEqual(code, 2, name)
            self.assertIn(name, err)
            env[name] = "   "
            self.assertEqual(run(env)[0], 2, name)

    def test_bad_ids_names_and_labels(self):
        self.refused(HUB_SUBSCRIPTION_ID="not-a-guid")
        self.refused(HUB_APIM_PRINCIPAL_ID="1234")
        for bad in ("rg name", "rg/x", "rg;x", "-", "a" * 91, "rg.", "$(x)"):
            self.refused(HUB_RESOURCE_GROUP=bad)
        for bad in ("Sweden Central", "sweden_central", "x", "https://x"):
            self.refused(HUB_LOCATION=bad)
        for bad in ('o"wner', "o<wner", "a" * 65, "o;wner", "o\nwner"):
            self.refused(HUB_OWNER=bad)

    def test_address_ranges_must_be_private_ipv4_and_nested(self):
        for bad in ("10.52.0.1/27", "10.52.0.0", "192.168.0.0/27", "8.8.8.0/27", "10.52.0.0/29", "10.52.0.0/8", "fd00::/64", "10.52.0.0/33", "x"):
            self.refused(HUB_VNET_PREFIX=bad, HUB_PE_SUBNET_PREFIX="10.52.0.0/29")
        for bad in ("10.53.0.0/28", "10.52.0.0/26", "10.52.0.0/30", "10.52.0.1/28", ""):
            self.refused(HUB_PE_SUBNET_PREFIX=bad)

    def test_dns_servers_must_be_private_ipv4_addresses(self):
        for bad in ("8.8.8.8", "10.20.0.4,8.8.8.8", "dns.example.com", "fd00::1", "10.20.0.4,,10.20.0.5", "1,2,3,4,5"):
            self.refused(HUB_DNS_SERVERS=bad)
        code, _, _, document = run({**ENV, "HUB_DNS_SERVERS": "10.20.0.4, 10.20.0.5"})
        self.assertEqual(document["parameters"]["dnsServers"]["value"], ["10.20.0.4", "10.20.0.5"])

    def test_budget_and_mail_addresses(self):
        for bad in ("0", "-5", "10001", "many", "1.5", ""):
            self.refused(HUB_BUDGET_AMOUNT=bad)
        for bad in ("not-a-mail", "a@b", "a@b.c", "a b@example.com", "a@example.com,", "a@example.com;b@example.com", "a@x.com," * 6 + "a@x.com"):
            self.refused(HUB_ALERT_EMAILS=bad)

    def test_the_messages_name_the_setting_and_never_echo_a_value(self):
        err = self.refused(HUB_OWNER='o"wner<secret>')
        self.assertIn("HUB_OWNER", err)
        self.assertNotIn("secret", err)


if __name__ == "__main__":
    unittest.main()
