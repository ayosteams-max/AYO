from types import MappingProxyType

# Infrastructure permissions only. Product and operations role matrices require
# explicit CEO/CTO policy approval and are not seeded by this mission.
PERMISSION_REGISTRY = MappingProxyType(
    {
        "authorization.permissions.read": "Read the authorization permission registry.",
        "authorization.roles.read": "Read authorization roles and their grants.",
        "authorization.roles.manage": "Create roles and manage role permissions.",
        "authorization.assignments.read": "Read identity role assignments.",
        "authorization.assignments.manage": "Assign and revoke identity roles.",
        "support.case.create": "Create a support case with approved structured details.",
        "support.case.read_assigned": "Read only support cases assigned to the service identity.",
        "support.case.update": "Update approved fields on an assigned support case.",
        "support.case.escalate": "Escalate a support case to trained human support.",
        "support.trip.read_limited": "Read the minimum approved trip support view.",
        "support.payment.read_status": "Read payment status without credentials or mutation authority.",
        "support.account.read_limited": "Read the minimum approved account support view.",
        "support.guidance.provide": "Provide approved low-risk support guidance.",
    }
)

AI_SUPPORT_PERMISSION_SET = frozenset(
    {
        "support.case.create",
        "support.case.read_assigned",
        "support.case.update",
        "support.case.escalate",
        "support.trip.read_limited",
        "support.payment.read_status",
        "support.account.read_limited",
        "support.guidance.provide",
    }
)
