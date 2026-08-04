from BACKEND.identity.models import IdentityType

FINANCIAL_HOLD_CREATE_PERMISSION = "financial.hold.create"
FINANCIAL_HOLD_REVIEW_PERMISSION = "financial.hold.review"
FINANCIAL_HOLD_RELEASE_PERMISSION = "financial.hold.release"
FINANCIAL_HOLD_ESCALATE_PERMISSION = "financial.hold.escalate"
FINANCIAL_HOLD_EXPIRE_PERMISSION = "financial.hold.expire"
FINANCIAL_HOLD_CANCEL_PERMISSION = "financial.hold.cancel"
FINANCIAL_HOLD_TRACE_READ_PERMISSION = "financial.hold.trace.read"
SUPPORT_FINANCIAL_HOLD_READ_STATUS_PERMISSION = "support.financial_hold.read_status"


def is_service_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.SERVICE
