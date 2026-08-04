from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.refund.application import RefundOrchestrationService


def build_refund_service(
    composition: PostgresRepositoryComposition,
) -> RefundOrchestrationService:
    return RefundOrchestrationService(composition)
