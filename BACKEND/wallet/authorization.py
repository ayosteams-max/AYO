from BACKEND.identity.models import IdentityType

WALLET_EVENT_CONSUME_PERMISSION = "wallet.event.consume"
WALLET_ACCOUNT_READ_OWN_PERMISSION = "wallet.account.read_own"
WALLET_TRACE_READ_PERMISSION = "wallet.trace.read"
SUPPORT_WALLET_READ_STATUS_PERMISSION = "support.wallet.read_status"


def is_service_identity(identity_type: IdentityType) -> bool:
    return identity_type is IdentityType.SERVICE
