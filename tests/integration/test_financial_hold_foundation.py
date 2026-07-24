from datetime import timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.financial_control.application import FinancialHoldApplicationService
from BACKEND.financial_control.engine import FinancialHoldConflict
from BACKEND.financial_control.models import (
    FinancialHoldCreateCommand,
    FinancialHoldReasonCode,
    FinancialHoldSourceType,
    FinancialHoldState,
    FinancialHoldTransitionCommand,
    FinancialHoldType,
    HoldReason,
)
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.tables import (
    financial_hold_events,
    financial_hold_outbox,
    financial_hold_state_history,
    ledger_entries,
    payment_attempts,
    settlement_batches,
    wallet_lineage_entries,
)
from tests.integration.test_payment_foundation import (
    NOW,
    create_identity,
    grant_permissions,
    subject,
)
from tests.integration.test_settlement_foundation import _captured_attempt

pytestmark = [pytest.mark.integration]


def _create_command(source_id, key):
    return FinancialHoldCreateCommand(
        hold_type=FinancialHoldType.RIDER_PAYMENT,
        source_type=FinancialHoldSourceType.PAYMENT_ATTEMPT,
        source_id=source_id,
        reason=HoldReason(
            reason_code=FinancialHoldReasonCode.PAYMENT_RISK_SIGNAL,
            reason_detail="gateway anomaly",
        ),
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=source_id,
        occurred_at=NOW,
    )


def _transition_command(state, key, reason_code, *, at=NOW):
    return FinancialHoldTransitionCommand(
        target_state=state,
        reason=HoldReason(reason_code=reason_code, reason_detail="workflow step"),
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        occurred_at=at,
    )


def test_increment14_hold_authority_idempotency_and_status_boundaries(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    support = create_identity(postgres_composition, IdentityType.STAFF)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    staff = create_identity(postgres_composition, IdentityType.STAFF)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.hold.create",
            "financial.hold.review",
            "financial.hold.release",
            "financial.hold.escalate",
            "financial.hold.expire",
            "financial.hold.cancel",
            "financial.hold.trace.read",
        ),
    )
    grant_permissions(
        postgres_composition,
        support,
        ("support.financial_hold.read_status",),
    )

    _, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    with postgres_composition.unit_of_work() as unit:
        financial_authority_before = {
            "ledger_entries": tuple(
                unit.connection.execute(select(ledger_entries)).mappings().all()
            ),
            "wallet_lineage_entries": tuple(
                unit.connection.execute(select(wallet_lineage_entries)).mappings().all()
            ),
            "payment_attempts": tuple(
                unit.connection.execute(select(payment_attempts)).mappings().all()
            ),
            "settlement_batches": tuple(
                unit.connection.execute(select(settlement_batches)).mappings().all()
            ),
        }
    holds = FinancialHoldApplicationService(postgres_composition)

    with pytest.raises(FinancialHoldConflict, match="access_denied"):
        holds.create_hold(
            subject(IdentityType.STAFF, staff.identity_id),
            _create_command(attempt.payment_attempt_id, f"hold-create-{uuid4()}"),
        )

    grant_permissions(postgres_composition, staff, ("financial.hold.create",))
    with pytest.raises(
        FinancialHoldConflict, match="financial_hold_service_identity_required"
    ):
        holds.create_hold(
            subject(IdentityType.STAFF, staff.identity_id),
            _create_command(attempt.payment_attempt_id, f"hold-create-{uuid4()}"),
        )

    key = f"hold-idem-{uuid4()}"
    created = holds.create_hold(
        subject(IdentityType.SERVICE, service.identity_id),
        _create_command(attempt.payment_attempt_id, key),
    )
    replay = holds.create_hold(
        subject(IdentityType.SERVICE, service.identity_id),
        _create_command(attempt.payment_attempt_id, key),
    )
    assert created.hold.hold_id == replay.hold.hold_id
    assert created.hold.state is FinancialHoldState.CREATED

    with pytest.raises(FinancialHoldConflict, match="idempotency_conflict"):
        holds.create_hold(
            subject(IdentityType.SERVICE, service.identity_id),
            FinancialHoldCreateCommand(
                hold_type=FinancialHoldType.RIDER_PAYMENT,
                source_type=FinancialHoldSourceType.PAYMENT_ATTEMPT,
                source_id=attempt.payment_attempt_id,
                reason=HoldReason(
                    reason_code=FinancialHoldReasonCode.PAYMENT_CHARGE_DISPUTE_RISK,
                    reason_detail="changed payload",
                ),
                idempotency_key=key,
                correlation_id=uuid4(),
                causation_id=attempt.payment_attempt_id,
                occurred_at=NOW,
            ),
        )

    status = holds.hold_status(
        subject(IdentityType.STAFF, support.identity_id),
        hold_id=created.hold.hold_id,
        at=NOW,
    )
    assert status.hold.hold_id == created.hold.hold_id
    assert len(status.history) == 1

    with pytest.raises(FinancialHoldConflict, match="financial_hold_status_not_found"):
        holds.hold_status(
            subject(IdentityType.RIDER, rider.identity_id),
            hold_id=created.hold.hold_id,
            at=NOW,
        )

    with pytest.raises(FinancialHoldConflict, match="financial_hold_lineage_missing"):
        holds.create_hold(
            subject(IdentityType.SERVICE, service.identity_id),
            _create_command(uuid4(), f"missing-lineage-{uuid4()}"),
        )

    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_hold_state_history)
            ).scalar_one()
            == 1
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_hold_events)
            ).scalar_one()
            == 1
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_hold_outbox)
            ).scalar_one()
            == 1
        )
        financial_authority_after = {
            "ledger_entries": tuple(
                unit.connection.execute(select(ledger_entries)).mappings().all()
            ),
            "wallet_lineage_entries": tuple(
                unit.connection.execute(select(wallet_lineage_entries)).mappings().all()
            ),
            "payment_attempts": tuple(
                unit.connection.execute(select(payment_attempts)).mappings().all()
            ),
            "settlement_batches": tuple(
                unit.connection.execute(select(settlement_batches)).mappings().all()
            ),
        }
    assert financial_authority_after == financial_authority_before


def test_increment14_hold_lifecycle_append_only_and_replay_safety(
    postgres_composition,
) -> None:
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.hold.create",
            "financial.hold.review",
            "financial.hold.release",
            "financial.hold.escalate",
            "financial.hold.expire",
            "financial.hold.cancel",
            "financial.hold.trace.read",
        ),
    )

    _, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    holds = FinancialHoldApplicationService(postgres_composition)
    actor = subject(IdentityType.SERVICE, service.identity_id)

    created = holds.create_hold(
        actor,
        _create_command(attempt.payment_attempt_id, f"hold-create-{uuid4()}"),
    )
    hold_id = created.hold.hold_id

    active_key = f"hold-active-{uuid4()}"
    holds.transition_hold(
        actor,
        hold_id=hold_id,
        command=_transition_command(
            FinancialHoldState.ACTIVE,
            active_key,
            FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=1),
        ),
    )
    history_after_first_active = holds.hold_status(
        actor, hold_id=hold_id, at=NOW
    ).history
    holds.transition_hold(
        actor,
        hold_id=hold_id,
        command=_transition_command(
            FinancialHoldState.ACTIVE,
            active_key,
            FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=1),
        ),
    )
    history_after_replay_active = holds.hold_status(
        actor, hold_id=hold_id, at=NOW
    ).history
    assert len(history_after_replay_active) == len(history_after_first_active)

    holds.transition_hold(
        actor,
        hold_id=hold_id,
        command=_transition_command(
            FinancialHoldState.UNDER_REVIEW,
            f"hold-review-{uuid4()}",
            FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=2),
        ),
    )
    holds.transition_hold(
        actor,
        hold_id=hold_id,
        command=_transition_command(
            FinancialHoldState.ESCALATED,
            f"hold-escalate-{uuid4()}",
            FinancialHoldReasonCode.COMPLIANCE_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=3),
        ),
    )
    released = holds.transition_hold(
        actor,
        hold_id=hold_id,
        command=_transition_command(
            FinancialHoldState.RELEASED,
            f"hold-release-{uuid4()}",
            FinancialHoldReasonCode.FINANCE_MANUAL_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=4),
        ),
    )
    assert released.hold.state is FinancialHoldState.RELEASED

    with pytest.raises(
        FinancialHoldConflict, match="financial_hold_transition_invalid"
    ):
        holds.transition_hold(
            actor,
            hold_id=hold_id,
            command=_transition_command(
                FinancialHoldState.ACTIVE,
                f"hold-reactivate-{uuid4()}",
                FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
                at=NOW + timedelta(seconds=5),
            ),
        )

    expired = holds.create_hold(
        actor,
        _create_command(attempt.payment_attempt_id, f"hold-expire-create-{uuid4()}"),
    )
    holds.transition_hold(
        actor,
        hold_id=expired.hold.hold_id,
        command=_transition_command(
            FinancialHoldState.ACTIVE,
            f"hold-expire-active-{uuid4()}",
            FinancialHoldReasonCode.SETTLEMENT_EXCEPTION_REVIEW,
            at=NOW + timedelta(seconds=1),
        ),
    )
    final_expired = holds.transition_hold(
        actor,
        hold_id=expired.hold.hold_id,
        command=_transition_command(
            FinancialHoldState.EXPIRED,
            f"hold-expire-{uuid4()}",
            FinancialHoldReasonCode.SETTLEMENT_EXCEPTION_REVIEW,
            at=NOW + timedelta(seconds=2),
        ),
    )
    assert final_expired.hold.state is FinancialHoldState.EXPIRED

    cancelled = holds.create_hold(
        actor,
        _create_command(attempt.payment_attempt_id, f"hold-cancel-create-{uuid4()}"),
    )
    final_cancelled = holds.transition_hold(
        actor,
        hold_id=cancelled.hold.hold_id,
        command=_transition_command(
            FinancialHoldState.CANCELLED,
            f"hold-cancel-{uuid4()}",
            FinancialHoldReasonCode.FINANCE_MANUAL_REVIEW_REQUIRED,
            at=NOW + timedelta(seconds=1),
        ),
    )
    assert final_cancelled.hold.state is FinancialHoldState.CANCELLED

    history = holds.hold_status(actor, hold_id=hold_id, at=NOW).history
    assert history[0].from_state is None
    assert history[0].to_state is FinancialHoldState.CREATED
    assert history[-1].to_state is FinancialHoldState.RELEASED

    with postgres_composition.unit_of_work() as unit:
        assert unit.connection.execute(
            select(func.count())
            .select_from(financial_hold_events)
            .where(financial_hold_events.c.aggregate_id == hold_id)
        ).scalar_one() == len(
            unit.connection.execute(
                select(financial_hold_state_history).where(
                    financial_hold_state_history.c.hold_id == hold_id
                )
            ).all()
        )


def test_increment14_lookup_authorization_and_lifecycle_characterization(
    postgres_composition,
) -> None:
    """Detect obvious local regressions; this is not a production-scale claim."""
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.hold.create",
            "financial.hold.review",
            "financial.hold.release",
            "financial.hold.trace.read",
        ),
    )
    _, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    actor = subject(IdentityType.SERVICE, service.identity_id)
    holds = FinancialHoldApplicationService(postgres_composition)
    hold = holds.create_hold(
        actor,
        _create_command(attempt.payment_attempt_id, f"perf-seed-{uuid4()}"),
    ).hold

    started = perf_counter()
    for _ in range(50):
        assert holds.hold_status(actor, hold_id=hold.hold_id, at=NOW).hold == hold
    lookup_seconds = perf_counter() - started

    started = perf_counter()
    for index in range(10):
        created = holds.create_hold(
            actor,
            _create_command(
                attempt.payment_attempt_id,
                f"perf-create-{index}-{uuid4()}",
            ),
        )
        active = holds.transition_hold(
            actor,
            hold_id=created.hold.hold_id,
            command=_transition_command(
                FinancialHoldState.ACTIVE,
                f"perf-active-{index}-{uuid4()}",
                FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
                at=NOW + timedelta(seconds=1),
            ),
        )
        reviewed = holds.transition_hold(
            actor,
            hold_id=active.hold.hold_id,
            command=_transition_command(
                FinancialHoldState.UNDER_REVIEW,
                f"perf-review-{index}-{uuid4()}",
                FinancialHoldReasonCode.FRAUD_REVIEW_REQUIRED,
                at=NOW + timedelta(seconds=2),
            ),
        )
        released = holds.transition_hold(
            actor,
            hold_id=reviewed.hold.hold_id,
            command=_transition_command(
                FinancialHoldState.RELEASED,
                f"perf-release-{index}-{uuid4()}",
                FinancialHoldReasonCode.FINANCE_MANUAL_REVIEW_REQUIRED,
                at=NOW + timedelta(seconds=3),
            ),
        )
        assert released.hold.state is FinancialHoldState.RELEASED
    lifecycle_seconds = perf_counter() - started

    assert lookup_seconds < 2.0
    assert lifecycle_seconds < 5.0
