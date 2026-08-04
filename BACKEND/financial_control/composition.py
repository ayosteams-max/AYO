from BACKEND.financial_control.application import FinancialHoldApplicationService
from BACKEND.persistence.composition import PostgresRepositoryComposition


def build_financial_hold_service(
    composition: PostgresRepositoryComposition,
) -> FinancialHoldApplicationService:
    return FinancialHoldApplicationService(composition)
