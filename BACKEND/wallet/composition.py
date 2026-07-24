from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.wallet.application import WalletOrchestrationService


def build_wallet_service(
    composition: PostgresRepositoryComposition,
) -> WalletOrchestrationService:
    return WalletOrchestrationService(composition)
