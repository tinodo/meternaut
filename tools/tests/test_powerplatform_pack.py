"""The solution of the Teams cards flow and the tool that packs it (powerplatform/solution/src, tools/powerplatform-pack.py; docs/proposals/19-teams-cards-through-power-automate.md).

What these tests say: the unpacked source packs clean, the zip is the same bytes every time and whatever the line endings of the checkout, it holds the parts that a solution zip holds and nothing else, the packer
refuses what would make the import fail, and no identifier of an environment, a tenant or a subscription, no address of the estate and no mail address is in the source or in the zip. Nothing is imported anywhere: the solution is
UNTESTED IN POWER PLATFORM, and no test here can say otherwise. The flow's own rules are in test_powerplatform_flow.py."""
import hashlib
import importlib.util
import io
import json
import re
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("powerplatform_pack_of_the_tests", ROOT / "tools" / "powerplatform-pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

SOURCE = ROOT / "powerplatform" / "solution" / "src"
WORKFLOW_ID = "e6272f40-4e93-4ef9-b20b-2fcd222057af"
FLOW = f"Workflows/MeternautCards-{WORKFLOW_ID.upper()}.json"
# The only identifiers in the solution: the flow's own id and the ids of the metadata of its trigger and actions, which were made for this solution and mean nothing outside it.
OWN_GUIDS = {
    WORKFLOW_ID,
    "4f6a9852-a482-4893-a75e-9e8c4e34d667", "75458fd0-36ac-4083-a7c9-e8e316b599ce", "eea68d7d-e530-4fd0-acb5-fc16764e8483", "247d1c9e-d687-431f-9e3b-570acf68c307",
    "05079912-4314-48ea-b9bb-deaafc81c321", "836fd17e-efa2-4ce3-89f6-51763127e9db", "d825f06b-9cce-4141-a731-8bdead3b6e1a", "ebc9ce71-1ba2-4a80-a576-898274f50d98",
    "92b5f918-c3c9-4a8b-8a22-62330cbd5548",
    # added with the card that closes itself: the condition, the update and its deletes and end, and the posted message with its end
    "3a1f6d52-7c1e-4b8a-9a43-0d6e2f8b5c71", "b7d94e18-52a3-4c06-8e1f-9a2c3d4e5f60", "c2e5a7f3-1b64-4d98-a0c7-6e8f9b1d2a35", "d9f3b1a6-8e27-4c5d-b4a0-7f1e6c2d9a84",
    "e4a8c6d2-3f19-4b7e-9d5a-2c8b0f6e1a97", "f1b7d3e9-6a42-4c8f-b2e0-5d9a7c3f8b16", "a5c9e1f7-2d38-4b60-8f4a-1e7d3b9c6a52", "b3d7f2a8-9c15-4e61-a7b4-6f0e8d2c1a39",
    "c8e2a4b6-1f73-4d95-9c08-3a5b7e1f2d64",
}
GUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
# The addresses that the solution may hold: the schemas of the file formats, and the example of a queue endpoint in the description of an environment variable (an invented account name).
ALLOWED_ADDRESSES = {
    "http://schemas.openxmlformats.org/package/2006/content-types",
    "http://www.w3.org/2001/XMLSchema-instance",
    "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "https://accountname.queue.core.windows.net/",
}
NAMES = ["Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json", "Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json.data.xml", "[Content_Types].xml",
         "customizations.xml", "solution.xml"]


def copy_of_the_source(target: Path, crlf: bool = False) -> Path:
    destination = target / "src"
    shutil.copytree(SOURCE, destination)
    if crlf:
        for path in destination.rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return destination


class TheSourcePacksClean(unittest.TestCase):
    def test_the_layout_is_the_reference_layout_and_nothing_more(self):
        files = sorted(p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file())
        self.assertEqual(files, ["Other/Customizations.xml", "Other/Relationships.xml", "Other/Solution.xml", f"{FLOW}", f"{FLOW}.data.xml"])

    def test_the_source_has_no_problem(self):
        parts = pack.collect(SOURCE)
        self.assertEqual(pack.check(parts), [])
        self.assertEqual(sorted(parts), ["Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json", "Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json.data.xml",
                                         "customizations.xml", "solution.xml"])

    def test_the_only_root_component_is_the_flow_and_nothing_else_is_one(self):
        solution = pack.xml_root("solution.xml", pack.collect(SOURCE)["solution.xml"])
        roots = solution.findall("./SolutionManifest/RootComponents/RootComponent")
        self.assertEqual([(r.get("type"), r.get("id")) for r in roots], [("29", "{" + WORKFLOW_ID + "}")])
        self.assertEqual(solution.findtext("./SolutionManifest/Managed"), "0", "unmanaged: the solution is the owner's to change")
        self.assertEqual(solution.findtext("./SolutionManifest/UniqueName"), "MeternautCards")

    def test_the_prefix_is_one_that_dataverse_takes(self):
        # A customization prefix is 2 to 8 letters and digits, starts with a letter and is not mscrm (Learn, "Customize table definitions"): the project's name has nine letters.
        solution = pack.xml_root("solution.xml", pack.collect(SOURCE)["solution.xml"])
        prefix = solution.findtext("./SolutionManifest/Publisher/CustomizationPrefix")
        self.assertRegex(prefix, r"^[a-z][a-z0-9]{1,7}$")
        self.assertFalse(prefix.startswith("mscrm"))
        customizations = pack.xml_root("customizations.xml", pack.collect(SOURCE)["customizations.xml"])
        names = [e.get("connectionreferencelogicalname") for e in customizations.findall("./connectionreferences/connectionreference")] + \
                [e.get("schemaname") for e in customizations.findall("./environmentvariabledefinitions/environmentvariabledefinition")]
        self.assertEqual(sorted(names), ["mtnaut_PostedQueueName", "mtnaut_QueueName", "mtnaut_StorageQueueEndpoint", "mtnaut_azurequeues", "mtnaut_teams"])
        for name in names:
            self.assertTrue(name.startswith(prefix + "_"), name)
        self.assertTrue(10000 <= int(solution.findtext("./SolutionManifest/Publisher/CustomizationOptionValuePrefix")) <= 99999, "an option value prefix is 10000 to 99999")

    def test_the_connection_references_are_the_two_connectors_and_hold_no_connection(self):
        customizations = pack.xml_root("customizations.xml", pack.collect(SOURCE)["customizations.xml"])
        references = {e.get("connectionreferencelogicalname"): e.findtext("connectorid") for e in customizations.findall("./connectionreferences/connectionreference")}
        self.assertEqual(references, {"mtnaut_azurequeues": "/providers/Microsoft.PowerApps/apis/shared_azurequeues", "mtnaut_teams": "/providers/Microsoft.PowerApps/apis/shared_teams"})
        self.assertEqual(customizations.findall(".//connectionid"), [])
        for definition in customizations.findall("./environmentvariabledefinitions/environmentvariabledefinition"):
            self.assertEqual(definition.findtext("type"), "100000000", "a string")
            self.assertEqual(definition.findtext("isrequired"), "1")
            self.assertIsNone(definition.find("defaultvalue"), "no value in the repository: the person who imports types it")
            self.assertEqual(definition.findtext("secretstore"), "0", "nothing here is a secret, and nothing secret is asked for")


class TheZipIsTheSameEveryTime(unittest.TestCase):
    def test_two_packs_are_the_same_bytes_and_a_checkout_with_crlf_makes_no_difference(self):
        first = pack.build(pack.collect(SOURCE))
        self.assertEqual(first, pack.build(pack.collect(SOURCE)))
        with tempfile.TemporaryDirectory() as tmp:
            crlf = pack.build(pack.collect(copy_of_the_source(Path(tmp), crlf=True)))
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(crlf).hexdigest(), "the line endings of the checkout are not in the zip")

    def test_the_zip_holds_the_parts_of_a_solution_in_a_fixed_order_with_fixed_times_and_no_folder_entry(self):
        with zipfile.ZipFile(io.BytesIO(pack.build(pack.collect(SOURCE)))) as archive:
            self.assertIsNone(archive.testzip())
            infos = archive.infolist()
            self.assertEqual([i.filename for i in infos], ["[Content_Types].xml", "Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json",
                                                           "Workflows/MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json.data.xml", "customizations.xml", "solution.xml"])
            self.assertEqual({i.date_time for i in infos}, {(1980, 1, 1, 0, 0, 0)})
            self.assertEqual({i.external_attr >> 16 for i in infos}, {0o644})
            self.assertEqual({i.create_system for i in infos}, {3})
            self.assertFalse([i for i in infos if i.is_dir()])
            for info in infos:
                data = archive.read(info.filename)
                self.assertNotIn(b"\r", data, "LF only")
                if info.filename.endswith(".json"):
                    json.loads(data)
                else:
                    pack.xml_root(info.filename, data)
            content_types = pack.xml_root("[Content_Types].xml", archive.read("[Content_Types].xml"))
            self.assertEqual({(e.get("Extension"), e.get("ContentType")) for e in content_types}, {("xml", "application/octet-stream"), ("json", "application/octet-stream")})

    def test_the_command_line_writes_the_zip_and_says_its_digest_and_check_writes_nothing(self):
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "meternaut-cards.zip"
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertEqual(pack.main(["--out", str(out)]), 0)
            self.assertTrue(out.is_file())
            self.assertIn(hashlib.sha256(out.read_bytes()).hexdigest(), printed.getvalue())
            other = Path(tmp) / "other.zip"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pack.main(["--check", "--out", str(other)]), 0)
            self.assertFalse(other.exists())

    def test_the_zip_folder_is_not_tracked(self):
        self.assertIn("/powerplatform/out/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


class NoIdentifierOfTheEstateIsInIt(unittest.TestCase):
    def texts(self):
        for path in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
            yield path.relative_to(SOURCE).as_posix(), path.read_text(encoding="utf-8")
        with zipfile.ZipFile(io.BytesIO(pack.build(pack.collect(SOURCE)))) as archive:
            for info in archive.infolist():
                yield "zip:" + info.filename, archive.read(info.filename).decode("utf-8")

    def test_the_only_identifiers_are_the_ones_that_were_made_for_this_solution(self):
        seen = set()
        for name, text in self.texts():
            for match in GUID.findall(text):
                self.assertIn(match.lower(), OWN_GUIDS, f"{name}: an identifier that is not this solution's own (an environment, a tenant, a subscription, an object or a connection?)")
                seen.add(match.lower())
        self.assertEqual(seen, OWN_GUIDS, "every id that was made for the solution is used")

    def test_no_address_of_an_estate_no_mail_address_and_no_value_that_could_be_a_secret(self):
        for name, text in self.texts():
            addresses = set(re.findall(r"https?://[^\s\"'<>)]+", text))
            self.assertLessEqual(addresses, ALLOWED_ADDRESSES, f"{name}: an address that is not a schema or the invented example")
            for pattern in (r"[\w.+-]+@[\w-]+\.[\w.-]+", r"(?i)onmicrosoft\.com", r"(?i)\.dynamics\.com", r"(?i)\.azurewebsites\.net", r"(?i)environment\.api\.powerplatform",
                            r"(?i)(?<!accountname)\.queue\.core\.windows\.net", r"(?i)accountkey|sharedaccesssignature|sig=|password|bearer |eyJ[A-Za-z0-9_-]{10,}"):
                self.assertIsNone(re.search(pattern, text), f"{name}: matches {pattern!r}")

    def test_the_source_names_no_other_project_of_the_owner_and_no_key(self):
        for name, text in self.texts():
            self.assertNotRegex(text, r"(?i)\blistKeys\b|\bkeyBasedAuth\b|\bsharedkey\b|\baccount key\b|connectionString", name)


class ThePackerRefusesWhatBreaksTheImport(unittest.TestCase):
    def refused(self, change, expected):
        with tempfile.TemporaryDirectory() as tmp:
            source = copy_of_the_source(Path(tmp))
            change(source)
            try:
                problems = pack.check(pack.collect(source))
            except pack.Problem as e:
                problems = [str(e)]
        self.assertTrue(any(expected in problem for problem in problems), f"{expected!r} not in {problems}")

    def test_a_file_that_the_layout_does_not_have(self):
        def change(source):
            (source / "environmentvariabledefinitions" / "mtnaut_QueueName").mkdir(parents=True)
            (source / "environmentvariabledefinitions" / "mtnaut_QueueName" / "environmentvariabledefinition.xml").write_text("<x/>", encoding="utf-8")
        self.refused(change, "is not a part of this layout")

    def test_an_xml_file_that_is_not_well_formed(self):
        self.refused(lambda source: (source / "Other" / "Solution.xml").write_text("<ImportExportXml>", encoding="utf-8"), "not well formed")

    def test_a_connection_reference_or_a_variable_as_a_root_component(self):
        def change(source):
            path = source / "Other" / "Solution.xml"
            path.write_text(path.read_text(encoding="utf-8").replace("</RootComponents>", '<RootComponent type="372" schemaName="mtnaut_teams" behavior="0" /></RootComponents>'), encoding="utf-8")
        self.refused(change, "root components of solution.xml are the cloud flows")

    def test_a_value_in_a_variable_definition(self):
        def change(source):
            path = source / "Other" / "Customizations.xml"
            path.write_text(path.read_text(encoding="utf-8").replace('<displayname default="Queue name">', "<defaultvalue>teams-cards</defaultvalue>\n      <displayname default=\"Queue name\">"), encoding="utf-8")
        self.refused(change, "has a value")

    def test_a_connection_in_a_connection_reference(self):
        def change(source):
            path = source / "Other" / "Customizations.xml"
            path.write_text(path.read_text(encoding="utf-8").replace("<iscustomizable>1</iscustomizable>\n      <statecode>0</statecode>", "<connectionid>x</connectionid><iscustomizable>1</iscustomizable>\n      <statecode>0</statecode>", 1), encoding="utf-8")
        self.refused(change, "names a connection")

    def test_a_flow_that_uses_what_the_file_does_not_define(self):
        def change(source):
            path = source / FLOW
            path.write_text(path.read_text(encoding="utf-8").replace("mtnaut_teams", "mtnaut_other"), encoding="utf-8")
        self.refused(change, "does not define")

    def test_a_flow_whose_data_file_names_another_flow(self):
        def change(source):
            path = source / f"{FLOW}.data.xml"
            path.write_text(path.read_text(encoding="utf-8").replace(WORKFLOW_ID, "00000000-0000-0000-0000-000000000000"), encoding="utf-8")
        self.refused(change, "WorkflowId is not the id in the file name")

    def test_a_missing_part(self):
        def change(source):
            (source / "Other" / "Solution.xml").unlink()
        self.refused(change, "solution.xml is missing")

    def test_the_command_line_refuses_with_a_message_and_writes_nothing(self):
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            source = copy_of_the_source(Path(tmp))
            (source / "Other" / "Solution.xml").write_text("<ImportExportXml>", encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(pack.main(["--src", str(source), "--out", str(Path(tmp) / "x.zip")]), 2)
            self.assertIn("error:", errors.getvalue())
            self.assertFalse((Path(tmp) / "x.zip").exists())


if __name__ == "__main__":
    unittest.main()
