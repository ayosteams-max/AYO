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
    }
)
