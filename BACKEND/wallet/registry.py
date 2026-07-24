from types import MappingProxyType

WALLET_PERMISSION_REGISTRY = MappingProxyType(
    {
        "wallet.event.consume": "Consume an authoritative financial lineage event into immutable wallet history.",
        "wallet.account.read_own": "Read own ETB wallet balances and immutable history.",
        "wallet.trace.read": "Read immutable wallet lineage and replay-safe event projections.",
        "support.wallet.read_status": "Read wallet status without mutation authority.",
    }
)
