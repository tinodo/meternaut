"""The reads that no Azure role at a subscription or a management group gives (environment/access-requirements.json, "tenantReads", T1 to T3), and the price sheet that R2 covers.

The capability profile (cases/capability.py) makes four reads. The price sheet of a subscription is read with the Cost Management Reader of R2. The lists of billing accounts, reservation orders and
savings plan orders are at the tenant or at a billing scope: a person gives them, with a role of Reservations, of Savings plans or of Billing, and the tool neither checks nor gives them.
"""
import copy
import json
import re
import unittest
from unittest import mock

import test_access_requirements as base

ar, MANIFEST, ROOT = base.ar, base.MANIFEST, base.ROOT
TENANT = ("billing-accounts-read", "reservation-orders-read", "savings-plan-orders-read")
PROPOSAL = ROOT / "docs" / "proposals" / "15-learning.md"


def loaded(document):
    """The loader's answer for a document, which it reads from a path: a stand-in that gives the text, so that nothing is written."""
    path = mock.Mock()
    path.read_text.return_value = json.dumps(document)
    return ar.load_manifest(path)


def refused(change) -> str:
    document = copy.deepcopy(json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8")))
    change(document)
    try:
        loaded(document)
    except ar.Problem as error:
        return str(error)
    raise AssertionError("the loader took a file that it should refuse")


class TheNewReads(unittest.TestCase):
    NAMES = base.TheCallsOfTheApp.NAMES

    def test_the_four_reads_are_gets_of_the_watch_and_each_is_listed_once_where_its_role_gives_it(self):
        watch = base.TheCallsOfTheApp().names_of(base.TheCallsOfTheApp.watch_calls(), "the Watch")
        for name in ("price-sheet-read", *TENANT):
            self.assertIn(name, watch)
        for method, pattern in base.TheCallsOfTheApp.watch_calls():
            text = pattern.pattern.replace("\\", "")
            if any(self.NAMES[name](method, text) for name in ("price-sheet-read", *TENANT)):
                self.assertEqual(method, "GET", text)
        grants = {g["id"]: g for g in MANIFEST["grants"]}
        self.assertIn("price-sheet-read", grants["R2"]["calls"], "Cost Management Reader holds Microsoft.Consumption/*/read")
        self.assertEqual(grants["R2"]["role"], "Cost Management Reader")
        for name in ("price-sheet-read", *TENANT):
            self.assertNotIn(name, grants["R1"]["calls"], "Reader at a subscription or a management group gives none of the four")
        for name in TENANT:
            self.assertFalse([g["id"] for g in MANIFEST["grants"] if name in g.get("calls", [])], f"{name} is no grant of an Azure role at the estate")

    def test_the_tenant_reads_are_three_ids_of_their_own_for_the_cases_identity_with_one_call_each(self):
        items = MANIFEST["tenantReads"]
        self.assertEqual([(item["id"], item["calls"]) for item in items], [("T1", ["billing-accounts-read"]), ("T2", ["reservation-orders-read"]), ("T3", ["savings-plan-orders-read"])])
        used = [g["id"] for g in MANIFEST["grants"]] + [r["id"] for r in MANIFEST["retired"]]
        self.assertFalse({item["id"] for item in items} & set(used))
        self.assertEqual({item["identity"] for item in items}, {"cases"})

    def test_they_name_the_roles_that_learn_gives_and_every_azure_role_they_name_only_reads(self):
        text = {item["id"]: " ".join(item["roles"]) for item in MANIFEST["tenantReads"]}
        self.assertIn("Billing account reader", text["T1"])
        self.assertIn("Enterprise administrator (read-only)", text["T1"])
        self.assertIn("not an Azure role", text["T1"])
        self.assertIn("Azure role: Reservations Reader, assigned at the tenant scope /providers/Microsoft.Capacity", text["T2"])
        self.assertIn("Azure role: Savings plan reader, assigned at the tenant scope /providers/Microsoft.BillingBenefits", text["T3"])
        for item in MANIFEST["tenantReads"]:
            for role in item["roles"]:
                for word in ("Administrator,", "Contributor", "Owner", "Purchaser", "Reservations Administrator", "Savings plan administrator"):
                    self.assertNotIn(word, role, f"{item['id']}: a role of the file only reads")

    def test_the_section_holds_no_guid_and_no_name_of_an_estate(self):
        text = json.dumps(MANIFEST["tenantReads"])
        self.assertEqual(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I), [])
        self.assertNotRegex(text, r"/subscriptions/|/resourceGroups/|billingAccounts/[A-Za-z0-9]")

    def test_the_tool_neither_checks_nor_gives_them_the_two_azure_grants_are_all_that_it_selects_and_the_table_of_the_proposal_is_the_same(self):
        self.assertEqual([g["id"] for g in ar.selected(MANIFEST, None)], ["R1", "R2"])
        self.assertEqual(len(ar.markdown(MANIFEST).splitlines()), 4)
        self.assertNotIn("T1", ar.markdown(MANIFEST))
        self.assertIn("price sheet", ar.markdown(MANIFEST), "R2 says that it covers the price sheet")


class TheLoader(unittest.TestCase):
    def test_a_tenant_read_must_be_complete_and_its_id_is_used_once(self):
        cases = (
            ("an id of a grant", lambda d: d["tenantReads"][0].update(id="R1"), "an id is used once"),
            ("an id of a retired item", lambda d: d["tenantReads"][0].update(id="W1"), "the id of a retired item is not the id of a grant, and is used once"),
            ("a repeated id", lambda d: d["tenantReads"][1].update(id="T1"), "an id is used once"),
            ("an unknown identity", lambda d: d["tenantReads"][0].update(identity="nobody"), "T1"),
            ("no text of what it reads", lambda d: d["tenantReads"][0].update(read=""), "T1"),
            ("no reason", lambda d: d["tenantReads"][0].update(why=""), "T1"),
            ("no call", lambda d: d["tenantReads"][0].update(calls=[]), "calls is a list of names"),
            ("a call that is not a name", lambda d: d["tenantReads"][0].update(calls=[5]), "calls is a list of names"),
            ("no role", lambda d: d["tenantReads"][0].update(roles=[]), "roles is a list of texts"),
            ("a role that is not a text", lambda d: d["tenantReads"][0].update(roles=[{"role": "x"}]), "roles is a list of texts"),
            ("a section that is not a list", lambda d: d.update(tenantReads={"T1": {}}), "tenantReads is a list"),
        )
        for label, change, words in cases:
            with self.subTest(label):
                self.assertIn(words, refused(change))

    def test_a_file_without_the_section_is_fine(self):
        document = json.loads((ROOT / "environment" / "access-requirements.json").read_text(encoding="utf-8"))
        del document["tenantReads"]
        self.assertEqual(ar.markdown_tenant(loaded(document)).splitlines(), ["| # | Read | Who can give it | What it is for |", "|---|---|---|---|"])


class TheTable(unittest.TestCase):
    def test_the_command_prints_the_table_with_an_option_and_it_reads_no_azure(self):
        lines = []
        code = ar.main(["markdown", "--tenant"], out=lines.append)
        self.assertEqual((code, "\n".join(lines)), (0, ar.markdown_tenant(MANIFEST)))
        self.assertEqual(len(ar.markdown_tenant(MANIFEST).splitlines()), 2 + len(MANIFEST["tenantReads"]))

    def test_the_proposal_shows_exactly_this_table(self):
        text = PROPOSAL.read_text(encoding="utf-8")
        match = re.search(r"<!-- access-tenant:start -->\n(.*?)\n<!-- access-tenant:end -->", text, re.S)
        self.assertIsNotNone(match, "the proposal has no marked table of the reads at the tenant")
        self.assertEqual(match.group(1), ar.markdown_tenant(MANIFEST), "run: python tools/access-requirements.py markdown --tenant, and paste it between the markers")


if __name__ == "__main__":
    unittest.main()
