from BACKEND.identity.models import IdentityType

FINANCIAL_POSTING_CREATE_PERMISSION = "financial.posting.create"
FINANCIAL_POSTING_TRACE_READ_PERMISSION = "financial.posting.trace.read"
SUPPORT_FINANCIAL_POSTING_READ_STATUS_PERMISSION = (
    "support.financial_posting.read_status"
)


def is_service_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.SERVICE
