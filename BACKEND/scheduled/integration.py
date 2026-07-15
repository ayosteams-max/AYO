import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import AssuranceLevel, IdentityType
from BACKEND.observability import MetricsSink, NullMetricsSink
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.scheduled.application import ScheduledRideApplication
from BACKEND.scheduled.engine import DeterministicScheduledStrategy, ReservationConflict
from BACKEND.scheduled.integration_models import (
    CreateScheduledReservationCommand,
    PassengerChannel,
    PublicReservation,
    UpdateReservationCommand,
)
from BACKEND.scheduled.models import (
    ConsentState,
    Participant,
    ParticipantKind,
    ParticipantRole,
    ReservationPolicy,
    ReservationState,
    ScheduledReservation,
)
from BACKEND.scheduled.observability import ScheduledObservability


def _public(item: ScheduledReservation) -> PublicReservation:
    return PublicReservation(
        reservation_id=item.reservation_id,
        state=item.state.value,
        pickup_place_id=item.pickup_place_id,
        destination_place_id=item.destination_place_id,
        service_type=item.service_type,
        requested_pickup_at=item.requested_pickup_at,
        requested_timezone=item.requested_timezone,
        version=item.version,
        requires_passenger_confirmation=(
            item.state is ReservationState.PASSENGER_CONFIRMATION_PENDING
        ),
    )


def _audit(
    item: ScheduledReservation,
    subject: AuthorizationSubject,
    action: str,
    reason: str,
) -> AuditEvent:
    return AuditEvent(
        actor_type=subject.actor_type,
        actor_id=str(subject.identity_id),
        session_id=subject.session_id,
        action=action,
        resource_type="scheduled_reservation",
        resource_id=str(item.reservation_id),
        outcome=AuditOutcome.SUCCESS,
        reason=reason,
        correlation_id=uuid4(),
        source_module="scheduled",
        safe_metadata={"policy_version": item.policy_version},
    )


class ScheduledIntegrationApplication:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        policy: ReservationPolicy,
        *,
        metrics: MetricsSink | None = None,
        pickup_secret: bytes,
        passenger_resolver: "VerifiedPassengerResolver | None" = None,
    ) -> None:
        if len(pickup_secret) < 32:
            raise ValueError("Pickup verification secret must contain 32 bytes")
        self._composition = composition
        self._policy = policy
        self._metrics = metrics or NullMetricsSink()
        self._observability = ScheduledObservability(self._metrics)
        self._pickup_secret = pickup_secret
        self._passenger_resolver = passenger_resolver or DenyPassengerResolver()

    def create(
        self,
        subject: AuthorizationSubject,
        command: CreateScheduledReservationCommand,
        *,
        idempotency_key: str,
        now: datetime,
    ) -> tuple[PublicReservation, bool]:
        self._require_type(subject, IdentityType.RIDER)
        booker = Participant(
            role=ParticipantRole.BOOKER,
            kind=ParticipantKind.IDENTITY,
            identity_id=subject.identity_id,
        )
        third_party = command.passenger_channel is not PassengerChannel.IDENTITY
        passenger = Participant(
            role=ParticipantRole.PASSENGER,
            kind={
                PassengerChannel.IDENTITY: ParticipantKind.IDENTITY,
                PassengerChannel.VERIFIED_CONTACT: ParticipantKind.VERIFIED_CONTACT,
                PassengerChannel.ASSISTED: ParticipantKind.ASSISTED,
            }[command.passenger_channel],
            identity_id=subject.identity_id if not third_party else None,
            contact_reference=(
                command.passenger_contact_reference if third_party else None
            ),
            consent_state=(
                ConsentState.PENDING
                if command.passenger_channel is PassengerChannel.VERIFIED_CONTACT
                else ConsentState.ASSISTED_REQUIRED
                if command.passenger_channel is PassengerChannel.ASSISTED
                else ConsentState.NOT_REQUIRED
            ),
        )
        participants = [booker, passenger]
        for role, reference in (
            (ParticipantRole.TRUSTED_CONTACT, command.trusted_contact_reference),
            (ParticipantRole.FUTURE_PAYER, command.future_payer_reference),
        ):
            if reference is not None:
                participants.append(
                    Participant(
                        role=role,
                        kind=ParticipantKind.VERIFIED_CONTACT,
                        contact_reference=reference,
                    )
                )
        item = ScheduledReservation(
            booker_id=subject.identity_id,
            passenger_participant_id=passenger.participant_id,
            pickup_place_id=command.pickup_place_id,
            destination_place_id=command.destination_place_id,
            service_type=command.service_type,
            quote_id=command.quote_id,
            requested_pickup_at=command.requested_pickup_at,
            requested_timezone=command.requested_timezone,
            state=(
                ReservationState.PASSENGER_CONFIRMATION_PENDING
                if third_party
                else ReservationState.ACCEPTED
            ),
            policy_id=self._policy.policy_id,
            policy_version=self._policy.version,
            created_at=now,
            updated_at=now,
        )
        with self._composition.unit_of_work() as unit:
            application = ScheduledRideApplication(
                unit.scheduled,
                DeterministicScheduledStrategy(self._policy),
                self._policy,
            )
            stored, created = application.create(
                item, tuple(participants), idempotency_key=idempotency_key, now=now
            )
        self._observability.outcome(
            "scheduled_reservation_creation",
            stored.reservation_id,
            "created" if created else "retry",
        )
        return _public(stored), created

    def read(
        self, subject: AuthorizationSubject, reservation_id: UUID
    ) -> PublicReservation:
        with self._composition.unit_of_work() as unit:
            item = self._owned(
                unit.scheduled, subject, reservation_id, allow_driver=True
            )
        return _public(item)

    def update(
        self,
        subject: AuthorizationSubject,
        reservation_id: UUID,
        command: UpdateReservationCommand,
        *,
        now: datetime,
    ) -> PublicReservation:
        self._require_step_up(subject)
        with self._composition.unit_of_work() as unit:
            item = self._owned(
                unit.scheduled, subject, reservation_id, booker_only=True
            )
            if item.state not in {
                ReservationState.PASSENGER_CONFIRMATION_PENDING,
                ReservationState.ACCEPTED,
            }:
                raise ReservationConflict("Reservation cannot be updated")
            values: dict[str, object] = {}
            if command.requested_pickup_at is not None:
                values["requested_pickup_at"] = command.requested_pickup_at
            if command.destination_place_id is not None:
                values["destination_place_id"] = command.destination_place_id
            stored = unit.scheduled.mutate(
                item,
                expected_version=command.expected_version,
                state=None,
                values=values,
                audit_event=_audit(
                    item, subject, "reservation.updated", "booker_update"
                ),
                event_type="reservation.updated",
                reason="booker_update",
                now=now,
            )
        return _public(stored)

    def confirm_or_decline(
        self,
        subject: AuthorizationSubject,
        reservation_id: UUID,
        *,
        confirmed: bool,
        now: datetime,
    ) -> PublicReservation:
        with self._composition.unit_of_work() as unit:
            item = unit.scheduled.get(reservation_id)
            if (
                item is None
                or item.state is not ReservationState.PASSENGER_CONFIRMATION_PENDING
            ):
                raise ReservationConflict("Reservation confirmation unavailable")
            passenger = next(
                part
                for part in unit.scheduled.participants(reservation_id)
                if part.role is ParticipantRole.PASSENGER
            )
            allowed = (
                passenger.identity_id == subject.identity_id
                or (
                    passenger.contact_reference is not None
                    and self._passenger_resolver.matches(
                        subject, passenger.contact_reference
                    )
                )
                or (
                    passenger.kind is ParticipantKind.ASSISTED
                    and subject.identity_type
                    in {IdentityType.STAFF, IdentityType.ADMINISTRATOR}
                    and subject.assurance_level is not AssuranceLevel.BASIC
                )
            )
            if not allowed:
                raise ReservationConflict("Passenger ownership required")
            consent = ConsentState.CONFIRMED if confirmed else ConsentState.DECLINED
            stored = unit.scheduled.record_consent(
                item,
                passenger,
                consent,
                expected_version=item.version,
                audit_event=_audit(
                    item,
                    subject,
                    f"reservation.passenger_{consent.value}",
                    f"passenger_{consent.value}",
                ),
                now=now,
            )
        self._observability.outcome(
            "scheduled_confirmation_outcomes",
            stored.reservation_id,
            consent.value,
        )
        return _public(stored)

    def cancel(
        self, subject: AuthorizationSubject, reservation_id: UUID, *, now: datetime
    ) -> PublicReservation:
        with self._composition.unit_of_work() as unit:
            item = self._owned(unit.scheduled, subject, reservation_id)
            if item.state in {
                ReservationState.ACTIVATED_AS_RIDE,
                ReservationState.FULFILLED,
            }:
                raise ReservationConflict("Reservation cannot be cancelled")
            stored = unit.scheduled.mutate(
                item,
                expected_version=item.version,
                state=ReservationState.RIDER_CANCELLED,
                values=None,
                audit_event=_audit(
                    item, subject, "reservation.cancelled", "authorized_cancellation"
                ),
                event_type="reservation.cancelled",
                reason="authorized_cancellation",
                now=now,
            )
        return _public(stored)

    def create_pickup_code(
        self, reservation_id: UUID, code: str, *, now: datetime
    ) -> None:
        digest = self._pickup_digest(reservation_id, code)
        with self._composition.unit_of_work() as unit:
            unit.scheduled.create_pickup_verification(
                reservation_id,
                code_hash=digest,
                expires_at=now + timedelta(minutes=10),
                now=now,
            )

    def verify_pickup(
        self,
        subject: AuthorizationSubject,
        reservation_id: UUID,
        code: str,
        *,
        now: datetime,
    ) -> PublicReservation:
        self._require_type(subject, IdentityType.DRIVER)
        digest = self._pickup_digest(reservation_id, code)
        with self._composition.unit_of_work() as unit:
            item = self._owned(
                unit.scheduled, subject, reservation_id, allow_driver=True
            )
            if (
                unit.scheduled.committed_driver_id(reservation_id)
                != subject.identity_id
            ):
                raise ReservationConflict("Driver ownership required")
            result = unit.scheduled.verify_pickup(
                item.reservation_id, code_hash=digest, now=now
            )
            if not result:
                raise ReservationConflict("Pickup verification failed")
            stored = unit.scheduled.mutate(
                item,
                expected_version=item.version,
                state=ReservationState.ACTIVATED_AS_RIDE,
                values={"activated_ride_id": uuid4()},
                audit_event=_audit(
                    item, subject, "reservation.activated_as_ride", "pickup_verified"
                ),
                event_type="reservation.activated_as_ride",
                reason="pickup_verified",
                now=now,
            )
        return _public(stored)

    def driver_commitment_response(
        self,
        subject: AuthorizationSubject,
        reservation_id: UUID,
        *,
        accepted: bool,
        expected_version: int,
        now: datetime,
    ) -> PublicReservation:
        self._require_type(subject, IdentityType.DRIVER)
        with self._composition.unit_of_work() as unit:
            item = self._owned(
                unit.scheduled, subject, reservation_id, allow_driver=True
            )
            if (
                unit.scheduled.committed_driver_id(reservation_id)
                != subject.identity_id
            ):
                raise ReservationConflict("Driver ownership required")
            target = None if accepted else ReservationState.REASSIGNING
            event = (
                "reservation.driver_committed"
                if accepted
                else "reservation.driver_commitment_declined"
            )
            stored = unit.scheduled.mutate(
                item,
                expected_version=expected_version,
                state=target,
                values=None,
                audit_event=_audit(
                    item, subject, event, "accepted" if accepted else "driver_declined"
                ),
                event_type=event,
                reason="accepted" if accepted else "driver_declined_no_penalty",
                now=now,
            )
        return _public(stored)

    def driver_progress(
        self,
        subject: AuthorizationSubject,
        reservation_id: UUID,
        *,
        ready: bool,
        now: datetime,
    ) -> PublicReservation:
        self._require_type(subject, IdentityType.DRIVER)
        with self._composition.unit_of_work() as unit:
            item = self._owned(
                unit.scheduled, subject, reservation_id, allow_driver=True
            )
            target = (
                ReservationState.READY_FOR_PICKUP
                if ready
                else ReservationState.DRIVER_EN_ROUTE
            )
            stored = unit.scheduled.mutate(
                item,
                expected_version=item.version,
                state=target,
                values=None,
                audit_event=_audit(
                    item, subject, f"reservation.{target.value}", target.value
                ),
                event_type=f"reservation.{target.value}",
                reason=target.value,
                now=now,
            )
        return _public(stored)

    def support_handoff(
        self, subject: AuthorizationSubject, reservation_id: UUID, *, now: datetime
    ) -> PublicReservation:
        if subject.identity_type not in {
            IdentityType.STAFF,
            IdentityType.ADMINISTRATOR,
        }:
            raise ReservationConflict("Support authorization required")
        self._require_step_up(subject)
        with self._composition.unit_of_work() as unit:
            item = unit.scheduled.get(reservation_id)
            if item is None:
                raise ReservationConflict("Reservation not found")
            stored = unit.scheduled.mutate(
                item,
                expected_version=item.version,
                state=None,
                values=None,
                audit_event=_audit(
                    item, subject, "reservation.support_handoff", "authorized_support"
                ),
                event_type="reservation.support_handoff",
                reason="authorized_support",
                now=now,
            )
        return _public(stored)

    def _pickup_digest(self, reservation_id: UUID, code: str) -> bytes:
        return hmac.new(
            self._pickup_secret,
            reservation_id.bytes + code.encode("ascii"),
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _require_type(subject: AuthorizationSubject, expected: IdentityType) -> None:
        if subject.identity_type is not expected:
            raise ReservationConflict("Identity type is not authorized")

    @staticmethod
    def _require_step_up(subject: AuthorizationSubject) -> None:
        if subject.assurance_level is AssuranceLevel.BASIC:
            raise ReservationConflict("Step-up authentication required")

    @staticmethod
    def _owned(
        repository, subject, reservation_id, *, booker_only=False, allow_driver=False
    ):
        item = repository.get(reservation_id)
        if item is None:
            raise ReservationConflict("Reservation not found")
        if item.booker_id == subject.identity_id:
            return item
        if not booker_only:
            passenger = next(
                (
                    p
                    for p in repository.participants(reservation_id)
                    if p.role is ParticipantRole.PASSENGER
                ),
                None,
            )
            if passenger is not None and passenger.identity_id == subject.identity_id:
                return item
        if (
            allow_driver
            and repository.committed_driver_id(reservation_id) == subject.identity_id
        ):
            return item
        raise ReservationConflict("Reservation ownership required")


class VerifiedPassengerResolver(Protocol):
    """Maps a trusted authenticated subject to an opaque verified contact reference."""

    def matches(
        self, subject: AuthorizationSubject, contact_reference: str
    ) -> bool: ...


class DenyPassengerResolver:
    def matches(self, subject: AuthorizationSubject, contact_reference: str) -> bool:
        del subject, contact_reference
        return False


class LocalVerifiedPassengerResolver:
    def __init__(self, links: dict[str, UUID]) -> None:
        self._links = dict(links)

    def matches(self, subject: AuthorizationSubject, contact_reference: str) -> bool:
        return self._links.get(contact_reference) == subject.identity_id
