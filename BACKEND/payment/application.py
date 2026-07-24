from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.ledger.models import LedgerJournal
from BACKEND.payment.engine import PaymentConflict
from BACKEND.payment.models import (
    PaymentAttempt,
    PaymentAttemptState,
    PaymentCallbackEnvelope,
    PaymentIntent,
    PaymentIntentState,
    PaymentMethodFamily,
    PaymentTraceability,
)
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.pricing.models import CalculationState, FareCalculation


class PaymentStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payment_intent: PaymentIntent
    payment_attempts: tuple[PaymentAttempt, ...]


class PaymentRideHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_id: UUID
    statuses: tuple[PaymentStatus, ...]


class CallbackOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    provider_event_id: str = Field(min_length=3, max_length=128)
    payload: dict[str, Any]


class PaymentOrchestrationService:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        callback_replay_window_seconds: int = 300,
    ) -> None:
        self._composition = composition
        self._callback_replay_window_seconds = callback_replay_window_seconds

    def validate_or_select_payment_method(
        self,
        subject: AuthorizationSubject,
        *,
        requested_method: PaymentMethodFamily,
        allow_cash: bool,
        at: datetime,
    ) -> PaymentMethodFamily:
        self._require_permission(subject, "payment.intent.create", at=at)
        if requested_method is PaymentMethodFamily.UNKNOWN:
            raise PaymentConflict("payment_method_unknown")
        if requested_method is PaymentMethodFamily.CASH and not allow_cash:
            raise PaymentConflict("payment_method_not_allowed")
        return requested_method

    def create_payment_intent(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        fare_calculation_id: UUID,
        ledger_journal_id: UUID,
        rider_identity_id: UUID,
        passenger_identity_id: UUID,
        booker_identity_id: UUID,
        payer_identity_id: UUID,
        method: PaymentMethodFamily,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        expires_at: datetime | None = None,
        metadata_safe: dict[str, str] | None = None,
        third_party_booking_authorized: bool = False,
    ) -> PaymentIntent:
        self._require_permission(subject, "payment.intent.create", at=at)
        self._validate_idempotency_key(idempotency_key)
        self._authorize_participants(
            subject,
            payer_identity_id=payer_identity_id,
            passenger_identity_id=passenger_identity_id,
            booker_identity_id=booker_identity_id,
            third_party_booking_authorized=third_party_booking_authorized,
            at=at,
        )
        selected = self.validate_or_select_payment_method(
            subject,
            requested_method=method,
            allow_cash=True,
            at=at,
        )

        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.payments.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="payment.intent.create",
                key=idempotency_key,
                payload={
                    "ride_id": str(ride_id),
                    "fare_calculation_id": str(fare_calculation_id),
                    "ledger_journal_id": str(ledger_journal_id),
                    "rider_identity_id": str(rider_identity_id),
                    "passenger_identity_id": str(passenger_identity_id),
                    "booker_identity_id": str(booker_identity_id),
                    "payer_identity_id": str(payer_identity_id),
                    "method": selected.value,
                    "expires_at": None
                    if expires_at is None
                    else expires_at.isoformat(),
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.payments.get_intent(canonical)
            if existing is not None:
                return existing

            calculation = unit.pricing.get_calculation(fare_calculation_id)
            journal = unit.ledger.get_journal(ledger_journal_id)
            calculation, _ = self._validate_authoritative_lineage(
                calculation=calculation,
                journal=journal,
                ride_id=ride_id,
                rider_identity_id=rider_identity_id,
                fare_calculation_id=fare_calculation_id,
            )

            amount_minor = calculation.breakdown.rider_total_minor
            if amount_minor < 0:
                raise PaymentConflict("payment_amount_invalid")

            trace = calculation.financial_traceability
            dispatch_handoff_id = trace.dispatch_handoff_id
            assignment_id = trace.assignment_id
            active_ride_id = trace.active_ride_id
            fare_calculation_chain_id = trace.fare_calculation_id
            if (
                dispatch_handoff_id is None
                or assignment_id is None
                or active_ride_id is None
                or fare_calculation_chain_id is None
            ):
                raise PaymentConflict("financial_lineage_conflict")

            intent = PaymentIntent(
                payment_intent_id=canonical,
                ride_id=ride_id,
                rider_identity_id=rider_identity_id,
                passenger_identity_id=passenger_identity_id,
                booker_identity_id=booker_identity_id,
                payer_identity_id=payer_identity_id,
                amount_minor=amount_minor,
                currency=calculation.breakdown.currency,
                payment_method_family=selected,
                state=PaymentIntentState.CREATED,
                traceability=PaymentTraceability(
                    ride_request_id=trace.ride_request_id,
                    dispatch_handoff_id=dispatch_handoff_id,
                    assignment_id=assignment_id,
                    active_ride_id=active_ride_id,
                    fare_estimate_id=trace.fare_estimate_id,
                    fare_calculation_id=fare_calculation_chain_id,
                    ledger_journal_id=ledger_journal_id,
                ),
                metadata_safe=metadata_safe or {},
                created_at=at,
                expires_at=expires_at,
            )
            return unit.payments.create_intent(intent)

    def create_payment_attempt(
        self,
        subject: AuthorizationSubject,
        *,
        payment_intent_id: UUID,
        provider_code: str,
        provider_reference: str,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> PaymentAttempt:
        self._require_permission(subject, "payment.attempt.execute", at=at)
        self._validate_idempotency_key(idempotency_key)

        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.payments.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="payment.attempt.create",
                key=idempotency_key,
                payload={
                    "payment_intent_id": str(payment_intent_id),
                    "provider_code": provider_code,
                    "provider_reference": provider_reference,
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.payments.get_attempt(canonical)
            if existing is not None:
                return existing

            intent = unit.payments.get_intent(payment_intent_id, lock=True)
            if intent is None:
                raise PaymentConflict("payment_intent_not_found")
            self._require_intent_status_read(subject, intent, at=at)
            if intent.expires_at is not None and at >= intent.expires_at:
                raise PaymentConflict("payment_intent_expired")
            if intent.state is not PaymentIntentState.CREATED:
                raise PaymentConflict("payment_intent_not_active")

            attempt = PaymentAttempt(
                payment_attempt_id=canonical,
                payment_intent_id=intent.payment_intent_id,
                provider_code=provider_code,
                provider_reference=provider_reference,
                state=PaymentAttemptState.CREATED,
                amount_minor=intent.amount_minor,
                currency=intent.currency,
                correlation_id=correlation_id,
                causation_id=causation_id,
                created_at=at,
                updated_at=at,
            )
            return unit.payments.create_attempt(attempt)

    def submit_provider_neutral_attempt(
        self,
        subject: AuthorizationSubject,
        *,
        payment_attempt_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PaymentAttempt:
        self._require_permission(subject, "payment.attempt.execute", at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.payments.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="payment.attempt.submit",
                key=idempotency_key,
                payload={"payment_attempt_id": str(payment_attempt_id)},
                response_reference=payment_attempt_id,
                at=at,
            )
            attempt = unit.payments.get_attempt(payment_attempt_id, lock=True)
            if attempt is None:
                raise PaymentConflict("payment_attempt_not_found")
            intent = unit.payments.get_intent(attempt.payment_intent_id, lock=True)
            if intent is None:
                raise PaymentConflict("payment_intent_not_found")
            self._require_intent_status_read(subject, intent, at=at)

            if intent.payment_method_family is PaymentMethodFamily.CASH:
                target = PaymentAttemptState.OUTCOME_UNKNOWN
                reason = "payment.cash.requires_reconciliation"
            else:
                target = PaymentAttemptState.AUTHORIZATION_PENDING
                reason = "payment.authorization.submitted"

            return unit.payments.transition_attempt(
                payment_attempt_id=attempt.payment_attempt_id,
                target_state=target,
                at=at,
                reason_code=reason,
                correlation_id=correlation_id,
                causation_id=attempt.payment_attempt_id,
            )

    def ingest_authenticated_callback_envelope(
        self,
        subject: AuthorizationSubject,
        *,
        payment_attempt_id: UUID,
        provider_code: str,
        signature_fingerprint: str,
        callback: CallbackOutcome,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PaymentAttempt:
        self._require_permission(subject, "payment.callback.ingest", at=at)
        if subject.identity_type is not IdentityType.SERVICE:
            raise PaymentConflict("access_denied")
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.payments.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="payment.callback.ingest",
                key=idempotency_key,
                payload={
                    "payment_attempt_id": str(payment_attempt_id),
                    "provider_code": provider_code,
                    "provider_event_id": callback.provider_event_id,
                    "outcome": callback.outcome,
                },
                response_reference=payment_attempt_id,
                at=at,
            )
            attempt = unit.payments.get_attempt(payment_attempt_id, lock=True)
            if attempt is None:
                raise PaymentConflict("payment_attempt_not_found")
            if attempt.provider_code != provider_code:
                raise PaymentConflict("payment_callback_provider_mismatch")

            envelope = unit.payments.ingest_callback_envelope(
                PaymentCallbackEnvelope(
                    provider_code=provider_code,
                    provider_event_id=callback.provider_event_id,
                    provider_signature_fingerprint=signature_fingerprint,
                    payload_hash=unit.payments.payload_hash(callback.payload),
                    received_at=at,
                    replay_window_ends_at=at
                    + timedelta(seconds=self._callback_replay_window_seconds),
                    correlated_attempt_id=attempt.payment_attempt_id,
                )
            )

            intent = unit.payments.get_intent(attempt.payment_intent_id, lock=True)
            if intent is None:
                raise PaymentConflict("payment_intent_not_found")
            target = self._callback_target_state(intent.payment_method_family, callback)
            changed = unit.payments.transition_attempt(
                payment_attempt_id=attempt.payment_attempt_id,
                target_state=target,
                at=at,
                reason_code=self._callback_reason(target),
                correlation_id=correlation_id,
                causation_id=attempt.payment_attempt_id,
                provider_event_id=callback.provider_event_id,
            )
            unit.payments.mark_callback_processed(
                callback_id=envelope.callback_id,
                correlated_attempt_id=attempt.payment_attempt_id,
                processed_at=at,
            )
            return changed

    def expire_intent(
        self,
        subject: AuthorizationSubject,
        *,
        payment_intent_id: UUID,
        reason_code: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PaymentIntent:
        self._require_permission(subject, "payment.attempt.execute", at=at)
        with self._composition.unit_of_work() as unit:
            intent = unit.payments.get_intent(payment_intent_id, lock=True)
            if intent is None:
                raise PaymentConflict("payment_intent_not_found")
            self._require_intent_status_read(subject, intent, at=at)
            return unit.payments.transition_intent(
                payment_intent_id=payment_intent_id,
                target_state=PaymentIntentState.EXPIRED,
                at=at,
                correlation_id=correlation_id,
                causation_id=payment_intent_id,
                reason_code=reason_code,
            )

    def cancel_intent(
        self,
        subject: AuthorizationSubject,
        *,
        payment_intent_id: UUID,
        reason_code: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PaymentIntent:
        self._require_permission(subject, "payment.attempt.execute", at=at)
        with self._composition.unit_of_work() as unit:
            intent = unit.payments.get_intent(payment_intent_id, lock=True)
            if intent is None:
                raise PaymentConflict("payment_intent_not_found")
            self._require_intent_status_read(subject, intent, at=at)
            attempts = unit.payments.list_attempts_for_intent(intent.payment_intent_id)
            if any(item.state is PaymentAttemptState.CAPTURED for item in attempts):
                raise PaymentConflict("payment_intent_cancel_forbidden")
            return unit.payments.transition_intent(
                payment_intent_id=payment_intent_id,
                target_state=PaymentIntentState.CANCELLED,
                at=at,
                correlation_id=correlation_id,
                causation_id=payment_intent_id,
                reason_code=reason_code,
            )

    def mark_reconciliation_required(
        self,
        subject: AuthorizationSubject,
        *,
        payment_attempt_id: UUID,
        reason_code: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PaymentAttempt:
        self._require_permission(subject, "payment.reconciliation.run", at=at)
        with self._composition.unit_of_work() as unit:
            return unit.payments.transition_attempt(
                payment_attempt_id=payment_attempt_id,
                target_state=PaymentAttemptState.OUTCOME_UNKNOWN,
                at=at,
                reason_code=reason_code,
                correlation_id=correlation_id,
                causation_id=payment_attempt_id,
            )

    def payment_status(
        self,
        subject: AuthorizationSubject,
        *,
        payment_intent_id: UUID,
        at: datetime,
    ) -> PaymentStatus:
        with self._composition.unit_of_work() as unit:
            intent = unit.payments.get_intent(payment_intent_id)
            if intent is None:
                raise PaymentConflict("payment_status_not_found")
            self._require_intent_status_read(subject, intent, at=at)
            attempts = unit.payments.list_attempts_for_intent(intent.payment_intent_id)
            return PaymentStatus(payment_intent=intent, payment_attempts=attempts)

    def payment_history_by_ride(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        at: datetime,
    ) -> PaymentRideHistory:
        with self._composition.unit_of_work() as unit:
            intents, attempts = unit.payments.payment_history_by_ride(ride_id)
            if not intents:
                raise PaymentConflict("payment_history_not_found")
            for intent in intents:
                self._require_intent_status_read(subject, intent, at=at)
            statuses = tuple(
                PaymentStatus(
                    payment_intent=intent,
                    payment_attempts=attempts.get(intent.payment_intent_id, tuple()),
                )
                for intent in intents
            )
            return PaymentRideHistory(ride_id=ride_id, statuses=statuses)

    def _require_permission(
        self, subject: AuthorizationSubject, permission: str, *, at: datetime
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, permission, at=at
            ):
                raise PaymentConflict("access_denied")

    def _authorize_participants(
        self,
        subject: AuthorizationSubject,
        *,
        payer_identity_id: UUID,
        passenger_identity_id: UUID,
        booker_identity_id: UUID,
        third_party_booking_authorized: bool,
        at: datetime,
    ) -> None:
        if subject.identity_id != payer_identity_id:
            raise PaymentConflict("payer_authority_required")
        if (
            booker_identity_id != payer_identity_id
            or passenger_identity_id != payer_identity_id
        ):
            if not third_party_booking_authorized:
                raise PaymentConflict("third_party_booking_authority_required")
            with self._composition.unit_of_work() as unit:
                allowed = unit.authorization.has_permission(
                    subject.identity_id, "scheduled.support.handoff", at=at
                )
            if not allowed:
                raise PaymentConflict("third_party_booking_authority_required")

    def _validate_authoritative_lineage(
        self,
        *,
        calculation: FareCalculation | None,
        journal: LedgerJournal | None,
        ride_id: UUID,
        rider_identity_id: UUID,
        fare_calculation_id: UUID,
    ) -> tuple[FareCalculation, LedgerJournal]:
        if calculation is None:
            raise PaymentConflict("fare_calculation_not_found")
        if calculation.state not in {
            CalculationState.FINAL_CALCULATED,
            CalculationState.CORRECTED,
        }:
            raise PaymentConflict("fare_calculation_not_payable")
        if calculation.ride_id != ride_id:
            raise PaymentConflict("financial_lineage_conflict")
        if calculation.rider_identity_id != rider_identity_id:
            raise PaymentConflict("financial_lineage_conflict")
        if calculation.calculation_id != fare_calculation_id:
            raise PaymentConflict("financial_lineage_conflict")
        trace = calculation.financial_traceability
        if (
            trace.active_ride_id != ride_id
            or trace.fare_calculation_id != calculation.calculation_id
            or trace.dispatch_handoff_id is None
            or trace.assignment_id is None
        ):
            raise PaymentConflict("financial_lineage_conflict")

        if journal is None:
            raise PaymentConflict("ledger_journal_not_found")
        if journal.business_event_id != calculation.calculation_id:
            raise PaymentConflict("ledger_lineage_conflict")
        journal_trace = journal.traceability
        if (
            journal_trace.active_ride_id != ride_id
            or journal_trace.fare_calculation_id != calculation.calculation_id
            or journal_trace.ride_request_id != trace.ride_request_id
            or journal_trace.dispatch_handoff_id != trace.dispatch_handoff_id
            or journal_trace.assignment_id != trace.assignment_id
            or journal_trace.fare_estimate_id != trace.fare_estimate_id
        ):
            raise PaymentConflict("ledger_lineage_conflict")
        return calculation, journal

    def _require_intent_status_read(
        self, subject: AuthorizationSubject, intent: PaymentIntent, *, at: datetime
    ) -> None:
        if (
            subject.identity_type is IdentityType.RIDER
            and subject.identity_id == intent.rider_identity_id
        ):
            with self._composition.unit_of_work() as unit:
                if unit.authorization.has_permission(
                    subject.identity_id, "payment.intent.read_own", at=at
                ):
                    return
        with self._composition.unit_of_work() as unit:
            if unit.authorization.has_permission(
                subject.identity_id, "support.payment.read_status", at=at
            ):
                return
            if unit.authorization.has_permission(
                subject.identity_id, "payment.trace.read", at=at
            ):
                return
        raise PaymentConflict("payment_status_not_found")

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not 16 <= len(value) <= 128:
            raise PaymentConflict("idempotency_key_invalid")

    @staticmethod
    def _callback_target_state(
        method: PaymentMethodFamily, callback: CallbackOutcome
    ) -> PaymentAttemptState:
        mapping = {
            "authorized": PaymentAttemptState.AUTHORIZED,
            "capture_pending": PaymentAttemptState.CAPTURE_PENDING,
            "captured": PaymentAttemptState.CAPTURED,
            "failed": PaymentAttemptState.FAILED,
            "cancelled": PaymentAttemptState.CANCELLED,
            "expired": PaymentAttemptState.EXPIRED,
            "unknown": PaymentAttemptState.OUTCOME_UNKNOWN,
        }
        target = mapping.get(callback.outcome)
        if target is None:
            raise PaymentConflict("payment_callback_outcome_invalid")
        if method is PaymentMethodFamily.CASH and target in {
            PaymentAttemptState.AUTHORIZED,
            PaymentAttemptState.CAPTURED,
        }:
            return PaymentAttemptState.OUTCOME_UNKNOWN
        return target

    @staticmethod
    def _callback_reason(target: PaymentAttemptState) -> str:
        return {
            PaymentAttemptState.AUTHORIZED: "payment.callback.authorized",
            PaymentAttemptState.CAPTURED: "payment.callback.captured",
            PaymentAttemptState.FAILED: "payment.callback.failed",
            PaymentAttemptState.CANCELLED: "payment.callback.cancelled",
            PaymentAttemptState.EXPIRED: "payment.callback.expired",
            PaymentAttemptState.OUTCOME_UNKNOWN: "payment.callback.reconciliation_required",
            PaymentAttemptState.AUTHORIZATION_PENDING: "payment.callback.authorization_pending",
            PaymentAttemptState.CAPTURE_PENDING: "payment.callback.capture_pending",
            PaymentAttemptState.CREATED: "payment.callback.created",
        }[target]
