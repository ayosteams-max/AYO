from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.wallet.models import WalletAccount, WalletLineageEntry


class WalletRepository(Protocol):
    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, str],
        response_reference: UUID,
        at: datetime,
    ) -> UUID: ...

    def get_account_by_owner(
        self, owner_identity_id: UUID, *, lock: bool = False
    ) -> WalletAccount | None: ...

    def get_or_create_account(
        self, *, owner_identity_id: UUID, at: datetime
    ) -> WalletAccount: ...

    def get_lineage_entry(self, wallet_entry_id: UUID) -> WalletLineageEntry | None: ...

    def append_lineage_entry(
        self,
        entry: WalletLineageEntry,
    ) -> WalletAccount: ...

    def list_lineage(
        self, wallet_account_id: UUID
    ) -> tuple[WalletLineageEntry, ...]: ...
