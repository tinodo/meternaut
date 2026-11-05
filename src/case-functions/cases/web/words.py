"""The words that a person reads for the states and the kinds of the records.

A word that is not listed here is shown as it is stored (escaped). Plain, short words: no figure of speech.
"""
from __future__ import annotations

# state -> (short word, what it means)
CASE_STATUS = {
    "proposed": ("Proposed", "A change is suggested. The first model recommended deleting the resource, the second model agreed, and no guard stopped it."),
    "needs_human": ("Needs a person", "A person has to look at it. A guard fired, the second model did not agree, or the first model was not sure enough."),
    "dropped": ("Dropped", "No change is suggested. The first model recommended keeping the resource."),
    "error": ("Error", "The case could not be finished. A check or a model call failed."),
    "awaiting_ok": ("Waiting for an OK", "A plan was made and waits for a person's OK."),
    "approved": ("Approved", "A person approved the plan and signed in to Azure. The change is being made now."),
    "running": ("Running", "The change has started and is not confirmed yet."),
    "done": ("Done", "The change was made."),
    "failed": ("Failed", "The change failed, or it was stopped before it started."),
    "declined": ("Declined", "A person said no. Nothing changed."),
    "expired": ("Expired", "Nobody answered in time. Nothing changed."),
    "verified": ("Done and verified", "The change was made and a later check confirmed it."),
}

PLAN_STATE = {
    "open": "Open. It waits for an OK.",
    "approved": "Approved. The change is being made now.",
    "consumed": "Used. The change was made with the approver's own permissions, and a plan runs once.",
    "declined": "Declined. Nothing changed.",
    "expired": "Expired. Nothing changed.",
    "withdrawn": "Withdrawn. Nothing changed.",
    "failed": "Failed. The change could not be finished.",
}

WITHDRAWN_ACTION = "Withdrawn before it started. Nothing changed."
ACTION_STATE = {
    "queued": "Queued. It has not started.",
    "running": "Running.",
    "done": "Done.",
    "failed": "Failed.",
    "unknown": "The result is not known yet.",
    "verified": "Done and verified.",
    "withdrawn": WITHDRAWN_ACTION,
}

# family -> the change in words, and what the resource is called in a sentence
FAMILY = {
    "delete-disk": ("Delete an unattached managed disk", "disk"),
    "delete-public-ip": ("Delete an unassigned public IP address", "public IP address"),
}

RESOURCE_TYPE = {
    "microsoft.compute/disks": "Managed disk",
    "microsoft.network/publicipaddresses": "Public IP address",
    "microsoft.network/privateendpoints": "Private endpoint",
    "microsoft.network/loadbalancers": "Load balancer",
    "microsoft.web/serverfarms": "App Service plan",
    "microsoft.compute/virtualmachines": "Virtual machine",
}

DETECTOR = {
    "orphan-private-endpoint": "A private endpoint with no approved connection",
    "orphan-managed-disk": "A managed disk that is not attached",
    "orphan-public-ip": "A public IP address that is not assigned",
    "load-balancer-without-backends": "A standard load balancer with no backend",
    "empty-app-service-plan": "An App Service plan with no app",
    "stopped-vm": "A virtual machine that is stopped",
    "advisor-cost": "A cost recommendation of Azure Advisor",
}

GUARD = {
    "locked": "A management lock covers the resource.",
    "keep-tag": "A tag asks to keep the resource.",
    "too-new": "The resource is less than 7 days old.",
    "managed-group": "A platform manages the resource group.",
    "unverified": "A guard could not be read, so it counts as on.",
}

DECISION = {
    "approve": "Your OK",
    "decline": "No, leave it as it is",
    "ask": "A question or suggestion",
    "not_mine": "Not mine",
}

# level -> (what the level is called, what it stops, the word for the button)
SWITCH = {
    "all": ("Everything", "No approval is accepted, no change is made in Azure and no message is sent.", "everything"),
    "changes": ("Changes", "No approval is accepted and no change is made in Azure.", "changes"),
    "messages": ("All messages", "No message is sent to anybody.", "all messages"),
}


def case_status(status: str) -> str:
    return CASE_STATUS.get(status, (status, ""))[0]


def family_words(family: str) -> str:
    return FAMILY.get(family, (family, ""))[0]


def resource_type_words(resource_type: str) -> str:
    return RESOURCE_TYPE.get((resource_type or "").lower(), "")
