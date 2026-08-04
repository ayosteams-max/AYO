import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.persistence.tables import (
    wallet_accounts,
    wallet_events,
    wallet_idempotency,
    wallet_lineage_entries,
    wallet_outbox,
)
from BACKEND.wallet.engine import WalletConflict, canonical_wallet_hash
from BACKEND.wallet.models import WalletAccount, WalletLineageEntry


def _account(row: Any) -> WalletAccount:
    return WalletAccount.model_validate(dict(row))


def _lineage(row: Any) -> WalletLineageEntry:
    return WalletLineageEntry.model_validate(dict(row))


class PostgresWalletRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, str],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = canonical_wallet_hash(payload)
        row = self._connection.execute(
            pg_insert(wallet_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(wallet_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(wallet_idempotency).where(
                    wallet_idempotency.c.actor_id == actor_id,
                    wallet_idempotency.c.operation == operation,
                    wallet_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise WalletConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def get_account_by_owner(
        self, owner_identity_id: UUID, *, lock: bool = False
    ) -> WalletAccount | None:
        query = select(wallet_accounts).where(
            wallet_accounts.c.owner_identity_id == owner_identity_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _account(row)

    def get_or_create_account(
        self,
        *,
        owner_identity_id: UUID,
        at: datetime,
    ) -> WalletAccount:
        existing = self.get_account_by_owner(owner_identity_id)
        if existing is not None:
            return existing
        created = WalletAccount(
            owner_identity_id=owner_identity_id,
            currency="ETB",
            available_minor=0,
            pending_minor=0,
            created_at=at,
            updated_at=at,
        )
        row = (
            self._connection.execute(
                pg_insert(wallet_accounts)
                .values(**created.model_dump(mode="json"))
                .on_conflict_do_nothing()
                .returning(wallet_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return _account(row)
        current = self.get_account_by_owner(owner_identity_id)
        if current is None:
            raise WalletConflict("wallet_account_not_found")
        return current

    def get_lineage_entry(self, wallet_entry_id: UUID) -> WalletLineageEntry | None:
        row = (
            self._connection.execute(
                select(wallet_lineage_entries).where(
                    wallet_lineage_entries.c.wallet_entry_id == wallet_entry_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _lineage(row)

    def append_lineage_entry(self, entry: WalletLineageEntry) -> WalletAccount:
        account = (
            self._connection.execute(
                select(wallet_accounts)
                .where(wallet_accounts.c.wallet_account_id == entry.wallet_account_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if account is None:
            raise WalletConflict("wallet_account_not_found")
        self._connection.execute(
            insert(wallet_lineage_entries).values(**entry.model_dump(mode="json"))
        )
        self._connection.execute(
            update(wallet_accounts)
            .where(wallet_accounts.c.wallet_account_id == entry.wallet_account_id)
            .values(
                available_minor=entry.resulting_available_minor,
                pending_minor=entry.resulting_pending_minor,
                updated_at=entry.recorded_at,
            )
        )
        self._event(entry)
        updated = (
            self._connection.execute(
                select(wallet_accounts).where(
                    wallet_accounts.c.wallet_account_id == entry.wallet_account_id
                )
            )
            .mappings()
            .one()
        )
        return _account(updated)

    def list_lineage(self, wallet_account_id: UUID) -> tuple[WalletLineageEntry, ...]:
        rows = self._connection.execute(
            select(wallet_lineage_entries)
            .where(wallet_lineage_entries.c.wallet_account_id == wallet_account_id)
            .order_by(
                wallet_lineage_entries.c.recorded_at,
                wallet_lineage_entries.c.wallet_entry_id,
            )
        ).mappings()
        return tuple(_lineage(row) for row in rows)

    def _event(self, entry: WalletLineageEntry) -> None:
        event_id = uuid4()
        self._connection.execute(
            insert(wallet_events).values(
                event_id=event_id,
                aggregate_type="wallet_account",
                aggregate_id=entry.wallet_account_id,
                event_type=f"wallet.{entry.entry_type.value}",
                schema_version=1,
                safe_payload={
                    "wallet_account_id": str(entry.wallet_account_id),
                    "wallet_entry_id": str(entry.wallet_entry_id),
                    "authoritative_source_type": entry.authoritative_source_type.value,
                    "authoritative_source_id": str(entry.authoritative_source_id),
                    "entry_type": entry.entry_type.value,
                    "amount_minor": entry.amount_minor,
                    "currency": entry.currency,
                },
                replay_payload={
                    "lineage_entry": entry.model_dump(mode="json"),
                },
                occurred_at=entry.recorded_at,
                correlation_id=entry.correlation_id,
                causation_id=entry.causation_id,
            )
        )
        self._connection.execute(
            insert(wallet_outbox).values(
                message_id=uuid4(),
                event_id=event_id,
                event_type=f"wallet.{entry.entry_type.value}",
                safe_payload={
                    "wallet_account_id": str(entry.wallet_account_id),
                    "wallet_entry_id": str(entry.wallet_entry_id),
                    "entry_type": entry.entry_type.value,
                },
                occurred_at=entry.recorded_at,
                available_at=entry.recorded_at,
                attempt_count=0,
            )
        )

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        return canonical_wallet_hash(json.loads(json.dumps(payload)))
