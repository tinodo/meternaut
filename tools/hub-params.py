#!/usr/bin/env python3
"""Builds the parameters of hub/main.bicep from the deployment workflow's settings (standard library only).

    python tools/hub-params.py --out "$RUNNER_TEMP/hub.parameters.json" >> "$GITHUB_OUTPUT"

The settings are environment variables, filled by the workflow from the repository's secrets and variables, so
that no address, name or mail address is in the repository:

    HUB_SUBSCRIPTION_ID, HUB_RESOURCE_GROUP, HUB_LOCATION, HUB_VNET_PREFIX, HUB_PE_SUBNET_PREFIX,
    HUB_DNS_SERVERS (comma separated), HUB_OWNER, HUB_BUDGET_AMOUNT, HUB_ALERT_EMAILS (comma separated),
    HUB_APIM_PRINCIPAL_ID

Every value is checked before anything is deployed. The name of the model account is worked out here, from the
subscription and the resource group, so it is the same on every run (a run after a removal finds, and the
workflow restores, the soft-deleted account of that name instead of leaving a second one behind).
It prints account_name=, private_endpoint=, vnet_name=, nsg_name= and endpoint= lines for GitHub to read as step
outputs; the workflow uses them to wait for, and to remove, exactly the resources hub/main.bicep names.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GROUP = re.compile(r"^[A-Za-z0-9._-]{1,89}[A-Za-z0-9_-]$")
LOCATION = re.compile(r"^[a-z0-9]{3,30}$")
OWNER = re.compile(r"^[A-Za-z0-9@._+ -]{1,64}$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PRIVATE_SPACE = ipaddress.ip_network("10.0.0.0/8")


class Problem(Exception):
    """A setting the owner can fix; printed without a trace."""


def need(env, name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise Problem(f"{name} is not set (a repository secret or variable of the deployment workflow)")
    return value


def network(value: str, name: str) -> ipaddress.IPv4Network:
    try:
        net = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise Problem(f"{name} is an address range such as 10.52.0.0/27, with the host bits zero")
    if not isinstance(net, ipaddress.IPv4Network):
        raise Problem(f"{name} is an IPv4 range")
    return net


def items(value: str, name: str, limit: int) -> list[str]:
    parts = [p.strip() for p in value.split(",")]
    if not 1 <= len(parts) <= limit or any(not p for p in parts):
        raise Problem(f"{name} is a comma-separated list of 1 to {limit} values")
    return parts


def account_name(subscription: str, group: str) -> str:
    digest = hashlib.sha256(f"{subscription}/{group}".lower().encode("utf-8")).hexdigest()
    return f"aif-meternaut-{digest[:8]}"


def build(env) -> tuple[dict, dict]:
    subscription = need(env, "HUB_SUBSCRIPTION_ID")
    group = need(env, "HUB_RESOURCE_GROUP")
    location = need(env, "HUB_LOCATION")
    principal = need(env, "HUB_APIM_PRINCIPAL_ID")
    owner = need(env, "HUB_OWNER")
    if not GUID.match(subscription):
        raise Problem("HUB_SUBSCRIPTION_ID is a subscription id")
    if not GROUP.match(group):
        raise Problem("HUB_RESOURCE_GROUP is a resource group name (letters, digits, . _ -)")
    if not LOCATION.match(location):
        raise Problem("HUB_LOCATION is a region name such as swedencentral")
    if not GUID.match(principal):
        raise Problem("HUB_APIM_PRINCIPAL_ID is the object id of the instance's system-assigned identity")
    if not OWNER.match(owner):
        raise Problem("HUB_OWNER is a short label (letters, digits, @ . _ + - and spaces)")

    vnet = network(need(env, "HUB_VNET_PREFIX"), "HUB_VNET_PREFIX")
    subnet = network(need(env, "HUB_PE_SUBNET_PREFIX"), "HUB_PE_SUBNET_PREFIX")
    if not vnet.subnet_of(PRIVATE_SPACE) or not 16 <= vnet.prefixlen <= 28:
        raise Problem("HUB_VNET_PREFIX is inside 10.0.0.0/8 and between /16 and /28")
    if not subnet.subnet_of(vnet) or subnet.prefixlen > 29:
        raise Problem("HUB_PE_SUBNET_PREFIX lies inside the virtual network and is at least a /29")

    dns = items(need(env, "HUB_DNS_SERVERS"), "HUB_DNS_SERVERS", 3)
    for server in dns:
        try:
            address = ipaddress.ip_address(server)
        except ValueError:
            raise Problem(f"HUB_DNS_SERVERS holds an address, not {server!r}")
        if address.version != 4 or not address.is_private:
            raise Problem("HUB_DNS_SERVERS holds private IPv4 addresses: the landing zone's resolver, not a public one")

    emails = items(need(env, "HUB_ALERT_EMAILS"), "HUB_ALERT_EMAILS", 5)
    if not all(EMAIL.match(e) for e in emails):
        raise Problem("HUB_ALERT_EMAILS holds mail addresses")
    try:
        budget = int(need(env, "HUB_BUDGET_AMOUNT"))
    except ValueError:
        budget = 0
    if not 1 <= budget <= 10000:
        raise Problem("HUB_BUDGET_AMOUNT is a whole number from 1 to 10000")

    name = account_name(subscription, group)
    parameters = {
        "location": location,
        "accountName": name,
        "vnetAddressPrefix": str(vnet),
        "peSubnetPrefix": str(subnet),
        "dnsServers": dns,
        "apimPrincipalId": principal.lower(),
        "owner": owner,
        "budgetAmount": budget,
        "alertEmails": emails,
    }
    outputs = {
        "account_name": name,
        "private_endpoint": f"pe-{name}",
        "vnet_name": "vnet-meternaut",
        "nsg_name": "nsg-meternaut-pe",
        "endpoint": f"https://{name}.cognitiveservices.azure.com",
    }
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "parameters": {k: {"value": v} for k, v in parameters.items()}}, outputs


def main(argv=None, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="where to write the ARM parameter file")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        document, outputs = build(environ)
    except Problem as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
