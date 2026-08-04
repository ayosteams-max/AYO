from types import MappingProxyType

FINANCIAL_POSTING_PERMISSION_REGISTRY = MappingProxyType(
    {
        "financial.posting.create": "Create an immutable balanced financial posting from authoritative lineage.",
        "financial.posting.trace.read": "Read immutable financial posting traces and replay-safe views.",
        "support.financial_posting.read_status": "Read financial posting status without mutation authority.",
    }
)
