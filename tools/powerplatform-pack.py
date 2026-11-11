#!/usr/bin/env python3
"""Packs the unpacked Power Platform solution into an unmanaged solution zip, the same bytes every time (standard library only).

    python tools/powerplatform-pack.py [--src powerplatform/solution/src] [--out powerplatform/out/meternaut-cards.zip] [--check]

The source is laid out as `pac solution unpack` lays out a solution (the layout of the owner's reference repository tinodo/secure-request-classifier, MIT, whose
scripts/Build-Solution.ps1 and Test-SolutionPackage.ps1 this does without the Power Platform CLI): Other/Solution.xml, Other/Customizations.xml (the connection references and the environment variable
definitions, inline: that is the only place that Dataverse wants them), Other/Relationships.xml (empty, and folded into Customizations.xml by the real packer) and Workflows/<name>-<GUID>.json with its
.json.data.xml. The zip holds [Content_Types].xml, customizations.xml, solution.xml and the Workflows folder, and nothing else.

What makes it the same every time: the entries are written in a fixed order ([Content_Types].xml first, then by name), every entry has the time 1980-01-01 00:00:00, the same attributes and the same
compression, and a line ending of a text file is always LF, whatever the checkout of the repository made of it. Two runs give the same bytes, and the tool prints the SHA-256 of them.

It refuses what would make the import fail, or what must not be in the repository (AGENTS.md rule 15 (e)): a file or a folder that the layout does not have, an XML file that is not well formed, a
root component that is not the cloud flow (a connection reference or an environment variable definition as a root component is what makes the import fail with a message that says nothing), a workflow whose
file name, id and data file disagree, a connection reference or an environment variable that the flow uses and the file does not define, and a value in an environment variable definition (the person who imports
the solution types the values, so that no address of an estate is in the repository). Nothing here is sent anywhere, and nothing is imported: the import is a hand step (tools/powerplatform.py steps).

It is NOT proven in Power Platform: the zip has never been imported by this repository.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "powerplatform" / "solution" / "src"
DEFAULT_OUTPUT = ROOT / "powerplatform" / "out" / "meternaut-cards.zip"

# What a solution zip of the maker portal and of `pac solution pack` holds for a solution with flows: the two parts are octet streams.
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/octet-stream" />'
    '<Default Extension="json" ContentType="application/octet-stream" />'
    "</Types>\n"
)
TIMESTAMP = (1980, 1, 1, 0, 0, 0)
GUID = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
WORKFLOW_FILE = re.compile(rf"^([A-Za-z0-9]+)-({GUID})\.json(\.data\.xml)?$")
# The order of the children of the root of customizations.xml: the real packer wants every one of them, even when it is empty, and in this sequence.
CUSTOMIZATIONS_ORDER = [
    "Entities", "Roles", "Workflows", "FieldSecurityProfiles", "Templates", "EntityMaps", "EntityRelationships", "OrganizationSettings", "optionsets", "CustomControls", "SolutionPluginAssemblies",
    "SdkMessageProcessingSteps", "ServiceEndpoints", "AppModuleSiteMaps", "AppModules", "EntityDataProviders", "CanvasApps", "Connectors", "connectionreferences", "environmentvariabledefinitions", "Languages",
]
WORKFLOW_ROOT_COMPONENT = "29"


class Problem(Exception):
    """A fault of the source that is printed without a trace."""


def read_text(path: Path) -> bytes:
    """The bytes of a text file with LF line endings: the checkout of a repository may have made them CRLF, and the zip must not depend on that."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def xml_root(name: str, data: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise Problem(f"{name} is not well formed XML: {e}")


def collect(source: Path) -> dict[str, bytes]:
    """The parts of the zip by name, from the unpacked source. Refuses a file that the layout does not have."""
    if not source.is_dir():
        raise Problem(f"{source} is not a folder: the unpacked solution is not there")
    found: dict[str, bytes] = {}
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        if relative == "Other/Solution.xml":
            found["solution.xml"] = read_text(path)
        elif relative == "Other/Customizations.xml":
            found["customizations.xml"] = read_text(path)
        elif relative == "Other/Relationships.xml":
            root = xml_root(relative, read_text(path))
            if len(root) or not root.tag.endswith("EntityRelationships"):
                raise Problem("Other/Relationships.xml holds a relationship: the real packer folds it into customizations.xml, this one packs none, so it is empty")
        elif relative.startswith("Workflows/") and relative.count("/") == 1 and WORKFLOW_FILE.match(path.name):
            found[relative] = read_text(path)
        else:
            raise Problem(f"{relative} is not a part of this layout: a component folder that is not folded into Other/Customizations.xml is copied into the zip as it is and breaks the import")
    for needed in ("solution.xml", "customizations.xml"):
        if needed not in found:
            raise Problem(f"{needed} is missing (Other/{'Solution' if needed == 'solution.xml' else 'Customizations'}.xml)")
    if not any(name.endswith(".json") for name in found):
        raise Problem("the solution has no flow: Workflows/<name>-<GUID>.json is missing")
    return found


def check(parts: dict[str, bytes]) -> list[str]:
    """What is wrong with the parts: an empty list is a source that the import can take, as far as a file can say (the import itself is not run)."""
    problems: list[str] = []
    try:
        solution = xml_root("solution.xml", parts["solution.xml"])
        customizations = xml_root("customizations.xml", parts["customizations.xml"])
        data_files = {n: xml_root(n, d) for n, d in parts.items() if n.endswith(".data.xml")}
        flows = {n: json.loads(d) for n, d in parts.items() if n.endswith(".json")}
    except (Problem, ValueError) as e:
        return [str(e)]

    roots = solution.findall("./SolutionManifest/RootComponents/RootComponent")
    if [r.get("type") for r in roots] != [WORKFLOW_ROOT_COMPONENT] * len(flows):
        problems.append("the root components of solution.xml are the cloud flows (type 29), one for each flow, and nothing else: a connection reference or an environment variable definition as a root component fails the import")
    root_ids = {(r.get("id") or "").strip("{}").lower() for r in roots}
    if (solution.findtext("./SolutionManifest/Managed") or "") != "0":
        problems.append("solution.xml is unmanaged (Managed 0)")

    if [child.tag for child in customizations] != CUSTOMIZATIONS_ORDER:
        problems.append("customizations.xml has every element of the layout, in the order of the real packer: " + ", ".join(CUSTOMIZATIONS_ORDER))
    references = {e.get("connectionreferencelogicalname"): e for e in customizations.findall("./connectionreferences/connectionreference")}
    definitions = {e.get("schemaname"): e for e in customizations.findall("./environmentvariabledefinitions/environmentvariabledefinition")}
    if not references or not definitions:
        problems.append("customizations.xml defines the flow's connection references and environment variables inline: it has none")
    for name, element in references.items():
        if element.find("connectionid") is not None:
            problems.append(f"the connection reference {name} names a connection: a connection belongs to a person and is bound by the person who imports the solution")
    for name, element in definitions.items():
        if element.find("defaultvalue") is not None or element.find("environmentvariablevalues") is not None:
            problems.append(f"the environment variable {name} has a value: the person who imports the solution types it, so that no address of an estate is in the repository")

    for name, flow in flows.items():
        file_id = WORKFLOW_FILE.match(Path(name).name).group(2).lower()  # type: ignore[union-attr]
        data_name = name + ".data.xml"
        if file_id not in root_ids:
            problems.append(f"{name}: its id is not a root component of solution.xml")
        data = data_files.get(data_name)
        if data is None:
            problems.append(f"{name} has no {data_name}")
        else:
            if (data.get("WorkflowId") or "").strip("{}").lower() != file_id:
                problems.append(f"{data_name}: WorkflowId is not the id in the file name")
            if (data.findtext("JsonFileName") or "").lower() != "/" + name.lower():
                problems.append(f"{data_name}: JsonFileName is not /{name}")
            if data.findtext("Category") != "5":
                problems.append(f"{data_name}: Category is 5, a modern cloud flow")
        properties = flow.get("properties", {})
        used = {ref.get("connection", {}).get("connectionReferenceLogicalName") for ref in properties.get("connectionReferences", {}).values()}
        for logical in sorted(used - set(references)):
            problems.append(f"{name} uses the connection reference {logical}, which customizations.xml does not define")
        parameters = properties.get("definition", {}).get("parameters", {})
        for key, parameter in parameters.items():
            schema = (parameter.get("metadata") or {}).get("schemaName")
            if schema and schema not in definitions:
                problems.append(f"{name} reads the environment variable {schema} ({key}), which customizations.xml does not define")
        text = json.dumps(properties.get("definition", {}))
        for schema in definitions:
            if f"({schema})" not in text:
                problems.append(f"the environment variable {schema} is defined and the flow does not read it")
    return problems


def build(parts: dict[str, bytes]) -> bytes:
    """The zip, byte for byte the same for the same parts: a fixed order, a fixed time, fixed attributes, a fixed compression."""
    entries = {"[Content_Types].xml": CONTENT_TYPES.encode("utf-8"), **parts}
    names = ["[Content_Types].xml"] + sorted(n for n in entries if n != "[Content_Types].xml")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name], compresslevel=9)
    return buffer.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", default=str(DEFAULT_SOURCE), help="the unpacked solution")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="the zip to write")
    parser.add_argument("--check", action="store_true", help="check the source and print what the zip would be, and write nothing")
    args = parser.parse_args(argv)
    try:
        parts = collect(Path(args.src))
        problems = check(parts)
        if problems:
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            return 2
        data = build(parts)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(data).hexdigest()
    if args.check:
        print(f"the source is a clean solution: {len(parts) + 1} parts, {len(data)} bytes, sha256 {digest}")
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"{out.name}: {len(parts) + 1} parts, {len(data)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
