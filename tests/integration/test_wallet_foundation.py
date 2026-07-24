from uuid import uuid4

import pytest

from BACKEND.identity.models import IdentityType
from BACKEND.settlement.application import SettlementOrchestrationService
from BACKEND.settlement.models import ReconciliationType
from BACKEND.wallet.application import WalletOrchestrationService
from BACKEND.wallet.engine import WalletConflict
from BACKEND.wallet.models import WalletAuthoritativeSourceType, WalletEntryType
from tests.integration.test_payment_foundation import (
    NOW,
    create_identity,
    grant_permissions,
    payable_context,
    subject,
)
from tests.integration.test_settlement_foundation import _captured_attempt

pytestmark = [pytest.mark.integration]


def test_increment12_wallet_authority_boundaries_and_status(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    support = create_identity(postgres_composition, IdentityType.STAFF)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        rider,
        ("wallet.account.read_own",),
    )
    grant_permissions(
        postgres_composition,
        support,
        ("support.wallet.read_status",),
    )
    grant_permissions(
        postgres_composition,
        service,
        ("wallet.event.consume", "wallet.trace.read"),
    )

    context = payable_context(postgres_composition)
    wallet = WalletOrchestrationService(postgres_composition)
    service_actor = subject(IdentityType.SERVICE, service.identity_id)

    account = wallet.consume_authoritative_event(
        service_actor,
        owner_identity_id=rider.identity_id,
        authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
        authoritative_source_id=context["journal"].journal_id,
        entry_type=WalletEntryType.PENDING_CREDIT,
        amount_minor=500,
        reason_code="wallet.pending.credit",
        idempotency_key=f"wallet-event-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=context["journal"].journal_id,
        at=NOW,
    )
    assert account.available_minor == 0
    assert account.pending_minor == 500

    with pytest.raises(WalletConflict, match="access_denied"):
        wallet.consume_authoritative_event(
            subject(IdentityType.STAFF, support.identity_id),
            owner_identity_id=rider.identity_id,
            authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
            authoritative_source_id=context["journal"].journal_id,
            entry_type=WalletEntryType.AVAILABLE_CREDIT,
            amount_minor=1,
            reason_code="wallet.denied",
            idempotency_key=f"wallet-event-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=context["journal"].journal_id,
            at=NOW,
        )

    rider_status = wallet.wallet_status(
        subject(IdentityType.RIDER, rider.identity_id),
        owner_identity_id=rider.identity_id,
        at=NOW,
    )
    support_status = wallet.wallet_status(
        subject(IdentityType.STAFF, support.identity_id),
        owner_identity_id=rider.identity_id,
        at=NOW,
    )
    assert (
        rider_status.account.wallet_account_id
        == support_status.account.wallet_account_id
    )
    assert len(rider_status.lineage) == 1


def test_increment12_wallet_idempotency_and_lineage_replay_safety(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        ("wallet.event.consume", "wallet.trace.read"),
    )
    grant_permissions(
        postgres_composition,
        rider,
        ("wallet.account.read_own",),
    )
    context = payable_context(postgres_composition)
    wallet = WalletOrchestrationService(postgres_composition)
    service_actor = subject(IdentityType.SERVICE, service.identity_id)
    key = f"wallet-idem-{uuid4()}"

    first = wallet.consume_authoritative_event(
        service_actor,
        owner_identity_id=rider.identity_id,
        authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
        authoritative_source_id=context["journal"].journal_id,
        entry_type=WalletEntryType.AVAILABLE_CREDIT,
        amount_minor=700,
        reason_code="wallet.available.credit",
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=context["journal"].journal_id,
        at=NOW,
    )
    second = wallet.consume_authoritative_event(
        service_actor,
        owner_identity_id=rider.identity_id,
        authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
        authoritative_source_id=context["journal"].journal_id,
        entry_type=WalletEntryType.AVAILABLE_CREDIT,
        amount_minor=700,
        reason_code="wallet.available.credit",
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=context["journal"].journal_id,
        at=NOW,
    )
    assert first.wallet_account_id == second.wallet_account_id
    status = wallet.wallet_status(
        subject(IdentityType.RIDER, rider.identity_id),
        owner_identity_id=rider.identity_id,
        at=NOW,
    )
    assert status.account.available_minor == 700
    assert len(status.lineage) == 1

    with pytest.raises(WalletConflict, match="idempotency_conflict"):
        wallet.consume_authoritative_event(
            service_actor,
            owner_identity_id=rider.identity_id,
            authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
            authoritative_source_id=context["journal"].journal_id,
            entry_type=WalletEntryType.AVAILABLE_CREDIT,
            amount_minor=701,
            reason_code="wallet.available.credit",
            idempotency_key=key,
            correlation_id=uuid4(),
            causation_id=context["journal"].journal_id,
            at=NOW,
        )


def test_increment12_wallet_authoritative_lineage_and_rollback_safety(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        ("wallet.event.consume", "wallet.trace.read", "settlement.batch.create"),
    )
    wallet = WalletOrchestrationService(postgres_composition)
    service_actor = subject(IdentityType.SERVICE, service.identity_id)

    with pytest.raises(WalletConflict, match="wallet_authoritative_source_not_found"):
        wallet.consume_authoritative_event(
            service_actor,
            owner_identity_id=rider.identity_id,
            authoritative_source_type=WalletAuthoritativeSourceType.SETTLEMENT_BATCH,
            authoritative_source_id=uuid4(),
            entry_type=WalletEntryType.PENDING_CREDIT,
            amount_minor=50,
            reason_code="wallet.missing.source",
            idempotency_key=f"wallet-missing-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )

    # Rollback safety: a failing unit of work must not persist a created account.
    with (
        pytest.raises(RuntimeError, match="force rollback"),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.wallets.get_or_create_account(owner_identity_id=rider.identity_id, at=NOW)
        raise RuntimeError("force rollback")

    with postgres_composition.unit_of_work() as unit:
        assert unit.wallets.get_account_by_owner(rider.identity_id) is None

    context, _, intent, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    settlement = SettlementOrchestrationService(postgres_composition)
    batch = settlement.create_batch(
        service_actor,
        idempotency_key=f"wallet-settlement-batch-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    settlement.collect_item(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=attempt.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        reconciliation_type=ReconciliationType.SETTLEMENT_RECONCILIATION,
        amount_minor=attempt.amount_minor,
        refund_request_id=None,
        idempotency_key=f"wallet-settlement-collect-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )

    created = wallet.consume_authoritative_event(
        service_actor,
        owner_identity_id=rider.identity_id,
        authoritative_source_type=WalletAuthoritativeSourceType.SETTLEMENT_BATCH,
        authoritative_source_id=batch.settlement_batch_id,
        entry_type=WalletEntryType.PENDING_CREDIT,
        amount_minor=attempt.amount_minor,
        reason_code="wallet.pending.credit",
        idempotency_key=f"wallet-settlement-consume-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=batch.settlement_batch_id,
        at=NOW,
    )
    assert created.pending_minor == attempt.amount_minor
