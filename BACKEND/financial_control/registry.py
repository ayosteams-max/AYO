from types import MappingProxyType

FINANCIAL_HOLD_PERMISSION_REGISTRY = MappingProxyType(
    {
        "financial.hold.create": "Create a financial hold that can block future money movement.",
        "financial.hold.review": "Move a financial hold into or out of under-review state.",
        "financial.hold.release": "Release a financial hold and allow future execution paths.",
        "financial.hold.escalate": "Escalate a financial hold for higher-authority manual review.",
        "financial.hold.expire": "Expire a financial hold based on authorized control policy.",
        "financial.hold.cancel": "Cancel a financial hold before release when justified.",
        "financial.hold.trace.read": "Read immutable financial hold traces and replay-safe views.",
        "support.financial_hold.read_status": "Read financial hold status without mutation authority.",
    }
)
