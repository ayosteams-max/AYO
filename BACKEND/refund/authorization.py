from BACKEND.identity.models import IdentityType

CUSTOMER_CREATE_PERMISSION = "refund.request.create"
SUPPORT_REVIEW_PERMISSION = "refund.review.perform"
RISK_INVESTIGATION_PERMISSION = "refund.investigation.perform"
FINANCE_APPROVAL_PERMISSION = "refund.approve"
SCHEDULING_PERMISSION = "refund.schedule"
WORKFLOW_COMPLETION_PERMISSION = "refund.workflow.run"
TRACE_READ_PERMISSION = "refund.trace.read"
SUPPORT_READ_PERMISSION = "support.refund.read_status"


def is_customer_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.RIDER


def is_service_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.SERVICE
