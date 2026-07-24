from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.access_models import OwnershipRelationship
from BACKEND.identity.account_access_service import AccountAccessService
from BACKEND.identity.models import IdentityType
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.engine import PaymentConflict
from BACKEND.payment.models import PaymentAttemptState, PaymentMethodFamily
from BACKEND.settlement.application import SettlementOrchestrationService
from BACKEND.settlement.engine import SettlementConflict
from BACKEND.settlement.models import (
    ReconciliationExceptionType,
    ReconciliationResult,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _AccountAccessService(AccountAccessService):
    test_unit: Any

    def _uow(self) -> Any:
        return nullcontext(self.test_unit)


def _subject(identity_type: IdentityType = IdentityType.RIDER) -> AuthorizationSubject:
    actor_type = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.SERVICE: ActorType.SERVICE,
    }[identity_type]
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=identity_type,
        actor_type=actor_type,
    )


def _service(service_type: type[Any], *, permission: bool = True) -> tuple[Any, Any]:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = permission
    composition: Any = MagicMock()
    composition.unit_of_work.side_effect = lambda: nullcontext(unit)
    return service_type(composition), unit


def test_identity_ownership_is_fail_closed_and_delegation_is_explicit() -> None:
    service = object.__new__(_AccountAccessService)
    owner, delegate, outsider = uuid4(), uuid4(), uuid4()
    resolver: Any = MagicMock()
    resolver.relationship.side_effect = lambda account_id, resource_type, resource_id: {
        owner: OwnershipRelationship.OWNER,
        delegate: OwnershipRelationship.DELEGATE,
    }.get(account_id, OwnershipRelationship.NONE)

    assert (
        service.authorize_ownership(
            account_id=owner,
            resource_type="ride_request",
            resource_id="ride-1",
            resolver=resolver,
        ).reason
        == "resource_owner"
    )
    assert (
        service.authorize_ownership(
            account_id=delegate,
            resource_type="ride_request",
            resource_id="ride-1",
            resolver=resolver,
        ).reason
        == "delegated_access"
    )
    assert not service.authorize_ownership(
        account_id=delegate,
        resource_type="ride_request",
        resource_id="ride-1",
        resolver=resolver,
        allow_delegate=False,
    ).allowed

    unit: Any = MagicMock()
    unit.access.has_permission.return_value = True
    service.test_unit = unit
    assert (
        service.authorize_ownership(
            account_id=outsider,
            resource_type="ride_request",
            resource_id="ride-1",
            resolver=resolver,
            request_administrative_override=True,
            at=NOW,
        ).reason
        == "explicit_administrative_override"
    )
    unit.access.has_permission.return_value = False
    assert not service.authorize_ownership(
        account_id=outsider,
        resource_type="ride_request",
        resource_id="ride-1",
        resolver=resolver,
        request_administrative_override=True,
        at=NOW,
    ).allowed


def test_payment_authority_method_and_callback_rules_fail_closed() -> None:
    service, unit = _service(PaymentOrchestrationService)
    rider = _subject()
    assert (
        service.validate_or_select_payment_method(
            rider,
            requested_method=PaymentMethodFamily.CASH,
            allow_cash=True,
            at=NOW,
        )
        is PaymentMethodFamily.CASH
    )
    with pytest.raises(PaymentConflict, match="payment_method_unknown"):
        service.validate_or_select_payment_method(
            rider,
            requested_method=PaymentMethodFamily.UNKNOWN,
            allow_cash=True,
            at=NOW,
        )
    with pytest.raises(PaymentConflict, match="payment_method_not_allowed"):
        service.validate_or_select_payment_method(
            rider,
            requested_method=PaymentMethodFamily.CASH,
            allow_cash=False,
            at=NOW,
        )

    unit.authorization.has_permission.return_value = False
    with pytest.raises(PaymentConflict, match="access_denied"):
        service.validate_or_select_payment_method(
            rider,
            requested_method=PaymentMethodFamily.CASH,
            allow_cash=True,
            at=NOW,
        )

    unit.authorization.has_permission.return_value = True
    other = uuid4()
    with pytest.raises(PaymentConflict, match="payer_authority_required"):
        service._authorize_participants(
            rider,
            payer_identity_id=other,
            passenger_identity_id=other,
            booker_identity_id=other,
            third_party_booking_authorized=True,
            at=NOW,
        )
    with pytest.raises(PaymentConflict, match="third_party_booking_authority_required"):
        service._authorize_participants(
            rider,
            payer_identity_id=rider.identity_id,
            passenger_identity_id=other,
            booker_identity_id=rider.identity_id,
            third_party_booking_authorized=False,
            at=NOW,
        )
    service._authorize_participants(
        rider,
        payer_identity_id=rider.identity_id,
        passenger_identity_id=other,
        booker_identity_id=rider.identity_id,
        third_party_booking_authorized=True,
        at=NOW,
    )

    callback = CallbackOutcome(
        outcome="captured", provider_event_id="event-1", payload={}
    )
    assert (
        service._callback_target_state(PaymentMethodFamily.CASH, callback)
        is PaymentAttemptState.OUTCOME_UNKNOWN
    )
    assert (
        service._callback_target_state(PaymentMethodFamily.CARD, callback)
        is PaymentAttemptState.CAPTURED
    )
    with pytest.raises(PaymentConflict, match="payment_callback_outcome_invalid"):
        service._callback_target_state(
            PaymentMethodFamily.CARD,
            callback.model_copy(update={"outcome": "unsupported"}),
        )


def test_settlement_permissions_idempotency_and_exception_mapping() -> None:
    service, unit = _service(SettlementOrchestrationService)
    subject = _subject(IdentityType.SERVICE)
    service._require_permission(subject, "settlement.batch.create", at=NOW)
    service._require_read(subject, at=NOW)

    unit.authorization.has_permission.return_value = False
    with pytest.raises(SettlementConflict, match="access_denied"):
        service._require_permission(subject, "settlement.batch.create", at=NOW)
    with pytest.raises(SettlementConflict, match="settlement_status_not_found"):
        service._require_read(subject, at=NOW)
    with pytest.raises(SettlementConflict, match="idempotency_key_invalid"):
        service._validate_idempotency_key("short")

    expected = {
        ReconciliationResult.MISMATCH: ReconciliationExceptionType.AMOUNT_MISMATCH,
        ReconciliationResult.MISSING: ReconciliationExceptionType.MISSING_CALLBACK,
        ReconciliationResult.DUPLICATE: ReconciliationExceptionType.DUPLICATE_PAYMENT,
        ReconciliationResult.MANUAL_REVIEW_REQUIRED: (
            ReconciliationExceptionType.MANUAL_INVESTIGATION
        ),
        ReconciliationResult.MATCHED: ReconciliationExceptionType.UNKNOWN_OUTCOME,
        ReconciliationResult.PARTIALLY_MATCHED: (
            ReconciliationExceptionType.REFUND_MISMATCH
        ),
    }
    assert {
        result: service._exception_from_result(result) for result in expected
    } == expected
