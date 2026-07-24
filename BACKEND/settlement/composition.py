from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.settlement.application import SettlementOrchestrationService


def build_settlement_service(
    composition: PostgresRepositoryComposition,
) -> SettlementOrchestrationService:
    return SettlementOrchestrationService(composition)
