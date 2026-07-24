from BACKEND.financial_posting.application import FinancialPostingApplicationService
from BACKEND.persistence.composition import PostgresRepositoryComposition


def build_financial_posting_service(
    composition: PostgresRepositoryComposition,
) -> FinancialPostingApplicationService:
    return FinancialPostingApplicationService(composition)
