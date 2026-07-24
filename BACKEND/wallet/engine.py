import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.payment.engine import PaymentConflict
from BACKEND.wallet.models import WalletEntryType


class WalletConflict(PaymentConflict):
    """Wallet foundation conflicts reuse existing fail-closed semantics."""


def canonical_wallet_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def apply_wallet_entry(
    *,
    available_minor: int,
    pending_minor: int,
    entry_type: WalletEntryType,
    amount_minor: int,
    at: datetime,
) -> tuple[int, int]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise WalletConflict("wallet_timestamp_invalid")
    if amount_minor < 0:
        raise WalletConflict("wallet_amount_invalid")

    if entry_type is WalletEntryType.PENDING_CREDIT:
        pending_minor += amount_minor
    elif entry_type is WalletEntryType.PENDING_RELEASE:
        if pending_minor < amount_minor:
            raise WalletConflict("wallet_pending_insufficient")
        pending_minor -= amount_minor
        available_minor += amount_minor
    elif entry_type is WalletEntryType.PENDING_REVERSAL:
        if pending_minor < amount_minor:
            raise WalletConflict("wallet_pending_insufficient")
        pending_minor -= amount_minor
    elif entry_type is WalletEntryType.AVAILABLE_CREDIT:
        available_minor += amount_minor
    elif entry_type is WalletEntryType.AVAILABLE_DEBIT:
        if available_minor < amount_minor:
            raise WalletConflict("wallet_available_insufficient")
        available_minor -= amount_minor
    else:
        raise WalletConflict("wallet_entry_type_invalid")

    if available_minor < 0 or pending_minor < 0:
        raise WalletConflict("wallet_balance_negative")
    return available_minor, pending_minor
