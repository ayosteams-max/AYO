from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.wallet.authorization import (
    SUPPORT_WALLET_READ_STATUS_PERMISSION,
    WALLET_ACCOUNT_READ_OWN_PERMISSION,
    WALLET_EVENT_CONSUME_PERMISSION,
    WALLET_TRACE_READ_PERMISSION,
    is_service_identity,
)
from BACKEND.wallet.engine import WalletConflict, apply_wallet_entry
from BACKEND.wallet.models import (
    WalletAccount,
    WalletAuthoritativeSourceType,
    WalletEntryType,
    WalletLineageEntry,
)


class WalletStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: WalletAccount
    lineage: tuple[WalletLineageEntry, ...]


class WalletOrchestrationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def consume_authoritative_event(
        self,
        subject: AuthorizationSubject,
        *,
        owner_identity_id: UUID,
        authoritative_source_type: WalletAuthoritativeSourceType,
        authoritative_source_id: UUID,
        entry_type: WalletEntryType,
        amount_minor: int,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> WalletAccount:
        with self._composition.unit_of_work() as unit:
            return self.consume_authoritative_event_with_unit(
                unit,
                subject,
                owner_identity_id=owner_identity_id,
                authoritative_source_type=authoritative_source_type,
                authoritative_source_id=authoritative_source_id,
                entry_type=entry_type,
                amount_minor=amount_minor,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                causation_id=causation_id,
                at=at,
            )

    def consume_authoritative_event_with_unit(
        self,
        unit: Any,
        subject: AuthorizationSubject,
        *,
        owner_identity_id: UUID,
        authoritative_source_type: WalletAuthoritativeSourceType,
        authoritative_source_id: UUID,
        entry_type: WalletEntryType,
        amount_minor: int,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> WalletAccount:
        self._require_permission_with_unit(
            unit, subject, WALLET_EVENT_CONSUME_PERMISSION, at=at
        )
        if not is_service_identity(subject.identity_type):
            raise WalletConflict("wallet_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        unit.wallets.get_or_create_account(
            owner_identity_id=owner_identity_id,
            at=at,
        )
        candidate_id = uuid4()
        canonical = unit.wallets.reserve_idempotency(
            actor_id=subject.identity_id,
            operation="wallet.event.consume",
            key=idempotency_key,
            payload={
                "owner_identity_id": str(owner_identity_id),
                "authoritative_source_type": authoritative_source_type.value,
                "authoritative_source_id": str(authoritative_source_id),
                "entry_type": entry_type.value,
                "amount_minor": str(amount_minor),
                "reason_code": reason_code,
            },
            response_reference=candidate_id,
            at=at,
        )
        existing = unit.wallets.get_lineage_entry(canonical)
        if existing is not None:
            replay = unit.wallets.get_account_by_owner(owner_identity_id)
            if replay is None:
                raise WalletConflict("wallet_account_not_found")
            return replay

        self._assert_authoritative_source_exists(
            unit,
            source_type=authoritative_source_type,
            source_id=authoritative_source_id,
        )
        locked = unit.wallets.get_account_by_owner(owner_identity_id, lock=True)
        if locked is None:
            raise WalletConflict("wallet_account_not_found")
        if locked.currency != "ETB":
            raise WalletConflict("wallet_currency_not_supported")

        next_available, next_pending = apply_wallet_entry(
            available_minor=locked.available_minor,
            pending_minor=locked.pending_minor,
            entry_type=entry_type,
            amount_minor=amount_minor,
            at=at,
        )
        entry = WalletLineageEntry(
            wallet_entry_id=canonical,
            wallet_account_id=locked.wallet_account_id,
            authoritative_source_type=authoritative_source_type,
            authoritative_source_id=authoritative_source_id,
            entry_type=entry_type,
            amount_minor=amount_minor,
            currency="ETB",
            resulting_available_minor=next_available,
            resulting_pending_minor=next_pending,
            reason_code=reason_code,
            recorded_by_identity_id=subject.identity_id,
            recorded_at=at,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return unit.wallets.append_lineage_entry(entry)

    def wallet_status(
        self,
        subject: AuthorizationSubject,
        *,
        owner_identity_id: UUID,
        at: datetime,
    ) -> WalletStatus:
        self._require_read(subject, owner_identity_id=owner_identity_id, at=at)
        with self._composition.unit_of_work() as unit:
            account = unit.wallets.get_account_by_owner(owner_identity_id)
            if account is None:
                raise WalletConflict("wallet_account_not_found")
            return WalletStatus(
                account=account,
                lineage=unit.wallets.list_lineage(account.wallet_account_id),
            )

    def _assert_authoritative_source_exists(
        self,
        unit,
        *,
        source_type: WalletAuthoritativeSourceType,
        source_id: UUID,
    ) -> None:
        if source_type is WalletAuthoritativeSourceType.LEDGER_JOURNAL:
            found = unit.ledger.get_journal(source_id) is not None
        elif source_type is WalletAuthoritativeSourceType.PAYMENT_ATTEMPT:
            found = unit.payments.get_attempt(source_id) is not None
        elif source_type is WalletAuthoritativeSourceType.REFUND_REQUEST:
            found = unit.refunds.get_request(source_id) is not None
        elif source_type is WalletAuthoritativeSourceType.SETTLEMENT_BATCH:
            found = unit.settlements.get_batch(source_id) is not None
        else:
            found = False
        if not found:
            raise WalletConflict("wallet_authoritative_source_not_found")

    def _require_permission(
        self, subject: AuthorizationSubject, permission: str, *, at: datetime
    ) -> None:
        with self._composition.unit_of_work() as unit:
            self._require_permission_with_unit(unit, subject, permission, at=at)

    @staticmethod
    def _require_permission_with_unit(
        unit: Any,
        subject: AuthorizationSubject,
        permission: str,
        *,
        at: datetime,
    ) -> None:
        if not unit.authorization.has_permission(
            subject.identity_id, permission, at=at
        ):
            raise WalletConflict("access_denied")

    def _require_read(
        self,
        subject: AuthorizationSubject,
        *,
        owner_identity_id: UUID,
        at: datetime,
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if (
                subject.identity_id == owner_identity_id
                and unit.authorization.has_permission(
                    subject.identity_id,
                    WALLET_ACCOUNT_READ_OWN_PERMISSION,
                    at=at,
                )
            ):
                return
            if unit.authorization.has_permission(
                subject.identity_id,
                WALLET_TRACE_READ_PERMISSION,
                at=at,
            ) or unit.authorization.has_permission(
                subject.identity_id,
                SUPPORT_WALLET_READ_STATUS_PERMISSION,
                at=at,
            ):
                return
        raise WalletConflict("wallet_status_not_found")

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not 16 <= len(value) <= 128:
            raise WalletConflict("idempotency_key_invalid")
