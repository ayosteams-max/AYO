from BACKEND.identity.models import IdentityType

SYSTEM_BATCH_CREATE_PERMISSION = "settlement.batch.create"
SYSTEM_COLLECT_PERMISSION = "settlement.collect.run"
SYSTEM_RECONCILE_PERMISSION = "settlement.reconcile.run"
FINANCE_READY_APPROVE_PERMISSION = "settlement.ready.approve"
FINANCE_READY_REJECT_PERMISSION = "settlement.ready.reject"
SYSTEM_EVIDENCE_RECORD_PERMISSION = "settlement.evidence.record"
RISK_EXCEPTION_INVESTIGATE_PERMISSION = "settlement.exception.investigate"
TRACE_READ_PERMISSION = "settlement.trace.read"
SUPPORT_READ_PERMISSION = "support.settlement.read_status"


def is_service_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.SERVICE
