from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import AccountStatus, IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.ride_request.engine import transition, validate_request
from BACKEND.ride_request.models import (
    Code,
    DestinationDefinition,
    PaymentIntentType,
    PickupDefinition,
    RideRequest,
    RideRequestState,
    RideServiceType,
    ValidationPolicy,
    ValidationStatus,
)


class RideRequestAccessDenied(RuntimeError):
    pass


class CreateRideRequestCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    client_request_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    pickup: PickupDefinition
    destination: DestinationDefinition
    service_type: RideServiceType = RideServiceType.IMMEDIATE_STANDARD
    payment_intent: PaymentIntentType = PaymentIntentType.CASH_COMPATIBLE
    consent_policy_version: Code


class RideRequestApplication:
    def __init__(
        self, composition: PostgresRepositoryComposition, policy: ValidationPolicy
    ) -> None:
        self._composition = composition
        self._policy = policy

    @staticmethod
    def _rider(subject: AuthorizationSubject) -> UUID:
        if (
            subject.identity_type is not IdentityType.RIDER
            or subject.actor_type is not ActorType.RIDER
        ):
            raise RideRequestAccessDenied("rider_authentication_required")
        return subject.identity_id

    def create(
        self,
        *,
        subject: AuthorizationSubject,
        command: CreateRideRequestCommand,
        at: datetime,
    ) -> RideRequest:
        rider_id = self._rider(subject)
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Server timestamp must be timezone-aware")
        at = at.astimezone(UTC)
        digest = sha256(
            command.model_dump_json(exclude={"idempotency_key"}).encode()
        ).hexdigest()
        request_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.ride_requests.reserve_idempotency(
                rider_identity_id=rider_id,
                operation="create",
                key=command.idempotency_key,
                request_hash=digest,
                response_reference=request_id,
                at=at,
            )
            existing = unit.ride_requests.get(canonical)
            if existing is not None:
                return existing
            zone = unit.ride_requests.find_zone(
                latitude=command.pickup.coordinate.latitude,
                longitude=command.pickup.coordinate.longitude,
                at=at,
            )
            request = RideRequest(
                request_id=canonical,
                client_request_id=command.client_request_id,
                rider_identity_id=rider_id,
                service_type=command.service_type,
                payment_intent=command.payment_intent,
                pickup_id=command.pickup.pickup_id,
                destination_id=command.destination.destination_id,
                service_zone_id=None if zone is None else zone.zone_id,
                consent_policy_version=command.consent_policy_version,
                created_at=at,
                updated_at=at,
                expires_at=at + timedelta(seconds=self._policy.request_ttl_seconds),
            )
            unit.ride_requests.create(request, command.pickup, command.destination)
            validating = transition(request, RideRequestState.VALIDATING, at=at)
            validating = unit.ride_requests.save(
                validating, expected_version=1, event_type="ride_request.validated"
            )
            identity = unit.identities.get(rider_id)
            decision = validate_request(
                request=validating,
                pickup=command.pickup,
                destination=command.destination,
                zone=zone,
                policy=self._policy,
                at=at,
                rider_active=identity is not None
                and identity.status is AccountStatus.ACTIVE,
                has_conflicting_request=unit.ride_requests.has_active(
                    rider_id, excluding=canonical
                ),
            )
            unit.ride_requests.append_validation(decision)
            target = (
                RideRequestState.READY_FOR_DISPATCH
                if decision.status is ValidationStatus.VALID
                else RideRequestState.VALIDATION_FAILED
            )
            event = (
                "ride_request.ready_for_dispatch"
                if target is RideRequestState.READY_FOR_DISPATCH
                else "ride_request.validation_failed"
            )
            result = unit.ride_requests.save(
                transition(validating, target, at=at),
                expected_version=2,
                event_type=event,
            )
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(rider_id),
                    session_id=subject.session_id,
                    action="ride_request.validation.completed",
                    resource_type="canonical_ride_request",
                    resource_id=str(result.request_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason=decision.reason_codes[0],
                    correlation_id=result.request_id,
                    source_module="ride_request",
                    safe_metadata={
                        "category": "ride_request",
                        "operation": "validation",
                        "policy_version": self._policy.version,
                        "state_to": result.state.value,
                    },
                )
            )
            return result

    def get_owned(
        self, *, subject: AuthorizationSubject, request_id: UUID
    ) -> RideRequest:
        rider_id = self._rider(subject)
        with self._composition.unit_of_work() as unit:
            request = unit.ride_requests.get(request_id)
            if request is None or request.rider_identity_id != rider_id:
                raise RideRequestAccessDenied("resource_access_denied")
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(rider_id),
                    session_id=subject.session_id,
                    action="ride_request.read",
                    resource_type="canonical_ride_request",
                    resource_id=str(request.request_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason="owned_read",
                    correlation_id=request.request_id,
                    source_module="ride_request",
                    safe_metadata={
                        "category": "ride_request",
                        "operation": "owned_read",
                        "state_to": request.state.value,
                    },
                )
            )
            return request

    def cancel(
        self,
        *,
        subject: AuthorizationSubject,
        request_id: UUID,
        reason_code: str,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> RideRequest:
        rider_id = self._rider(subject)
        if not 8 <= len(idempotency_key) <= 128:
            raise ValueError("Idempotency key length is invalid")
        digest = sha256(
            f"{request_id}:{reason_code}:{expected_version}".encode()
        ).hexdigest()
        with self._composition.unit_of_work() as unit:
            canonical = unit.ride_requests.reserve_idempotency(
                rider_identity_id=rider_id,
                operation="cancel",
                key=idempotency_key,
                request_hash=digest,
                response_reference=request_id,
                at=at,
            )
            request = unit.ride_requests.get(canonical)
            if request is None or request.rider_identity_id != rider_id:
                raise RideRequestAccessDenied("resource_access_denied")
            if request.state is RideRequestState.CANCELLED:
                return request
            if request.version != expected_version:
                raise ValueError("stale_aggregate_version")
            cancelled = transition(
                request,
                RideRequestState.CANCELLED,
                at=at,
                cancellation_reason=reason_code,
            )
            result = unit.ride_requests.save(
                cancelled,
                expected_version=expected_version,
                event_type="ride_request.cancelled",
            )
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(rider_id),
                    session_id=subject.session_id,
                    action="ride_request.cancelled",
                    resource_type="canonical_ride_request",
                    resource_id=str(result.request_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason=reason_code,
                    correlation_id=result.request_id,
                    source_module="ride_request",
                    safe_metadata={
                        "category": "ride_request",
                        "operation": "cancel",
                        "state_from": request.state.value,
                        "state_to": result.state.value,
                    },
                )
            )
            return result
