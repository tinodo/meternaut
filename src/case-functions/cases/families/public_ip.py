"""The family of an unassigned public IP address: delete it. It behaves as it did when it was written in runner.py and approvals.py."""
from __future__ import annotations

from . import calls
from .delete import DeleteFamily


class DeletePublicIp(DeleteFamily):
    name = "delete-public-ip"
    summary = "delete an unassigned public IP address"
    kinds = (calls.PUBLIC_IP,)
    recommendations = ("delete",)
    detectors = ("orphan-public-ip",)

    def why_not_idle(self, located, resource: dict) -> str | None:
        properties = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
        if properties.get("ipConfiguration") or properties.get("natGateway") or properties.get("linkedPublicIPAddress"):
            return "the public IP address is not unassigned any more"
        return None
