from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.support.models import SupportQueue
from BACKEND.support.service import (
    QUEUE_PERMISSIONS,
    SupportAccessDenied,
    SupportService,
)


class SupportEvidenceAuditSink(Protocol):
    def record(
        self,
        *,
        actor_identity_id: UUID,
        case_id: UUID,
        ride_id: UUID,
        purpose: str,
        allowed: bool,
        at: datetime,
    ) -> None: ...


class SupportRideEvidenceProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_id: UUID
    ride_request_id: UUID
    rider_reference: UUID
    driver_reference: UUID | None
    service_type: str
    pickup_reference: str
    destination_reference: str
    lifecycle_state: str
    lifecycle_last_sequence: int
    dispatch_handoff_id: UUID | None
    assignment_id: UUID | None
    pricing_policy_version: str | None
    fare_estimate_id: UUID | None
    estimate_acceptance_id: UUID | None
    fare_calculation_id: UUID | None
    gross_fare_minor: int | None
    payment_classification: str | None
    cash_evidence_state: str | None
    cash_accounting_state: str | None
    cash_reconciliation_state: str | None
    ledger_journal_id: UUID | None
    rider_receipt_available: bool
    driver_receipt_available: bool
    reason_codes: tuple[str, ...] = ()
    completeness: str = Field(pattern=r"^(complete|incomplete)$")
    missing_authority: tuple[str, ...] = ()


class SupportRideEvidenceApplication:
    """Read-time, purpose-bound projection; no Support-owned ride state."""

    _SENSITIVE = frozenset(
        {
            SupportQueue.FINANCE,
            SupportQueue.FRAUD,
            SupportQueue.SAFETY,
            SupportQueue.LEGAL,
        }
    )

    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        audit: SupportEvidenceAuditSink,
    ) -> None:
        self._composition = composition
        self._audit = audit
        self._support = SupportService()

    def project(
        self,
        *,
        subject: AuthorizationSubject,
        case_id: UUID,
        ride_id: UUID,
        purpose: str,
        step_up_verified: bool,
        at: datetime,
    ) -> SupportRideEvidenceProjection:
        allowed = False
        try:
            if subject.identity_type not in {
                IdentityType.STAFF,
                IdentityType.ADMINISTRATOR,
                IdentityType.SERVICE,
            }:
                raise SupportAccessDenied("Support access denied")
            if (
                not 3 <= len(purpose) <= 63
                or not purpose.replace("_", ".")
                .replace("-", ".")
                .replace(".", "a")
                .isalnum()
            ):
                raise SupportAccessDenied("Support access denied")
            with self._composition.unit_of_work() as unit:
                case = unit.support.get_case(case_id)
                if case is None:
                    raise SupportAccessDenied("Support access denied")
                self._support.require_read(unit, case, subject)
                if not unit.authorization.has_permission(
                    subject.identity_id, "support.trip.read_limited", at=at
                ):
                    raise SupportAccessDenied("Support access denied")
                if case.related_ride_reference != str(ride_id):
                    raise SupportAccessDenied("Support access denied")
                if case.assigned_queue in self._SENSITIVE and not step_up_verified:
                    raise SupportAccessDenied("Support access denied")
                if not unit.authorization.has_permission(
                    subject.identity_id, QUEUE_PERMISSIONS[case.assigned_queue], at=at
                ):
                    raise SupportAccessDenied("Support access denied")
                ride = unit.active_rides.get(ride_id)
                if ride is None or ride.ride_request_id is None:
                    raise SupportAccessDenied("Support access denied")
                handoff = (
                    unit.handoff_dispatch.get_handoff(ride.dispatch_handoff_id)
                    if ride.dispatch_handoff_id is not None
                    else None
                )
                journey = unit.pricing.financial_journey(ride_id)
                record = unit.post_trip.get(ride_id)
                package = unit.post_trip.package_for_ride(ride_id)
                accounting = unit.post_trip.cash_accounting_record(ride_id)
                cash_evidence = unit.post_trip.cash_collection_evidence(ride_id)
                missing: list[str] = []
                if handoff is None:
                    missing.append("dispatch")
                if journey is None or not journey.fare_estimates:
                    missing.append("pricing_estimate")
                if journey is None or not journey.fare_calculations:
                    missing.append("pricing_final")
                if record is None or package is None:
                    missing.append("post_trip")
                estimate = (
                    None
                    if journey is None or not journey.fare_estimates
                    else journey.fare_estimates[-1]
                )
                calculation = (
                    None
                    if journey is None or not journey.fare_calculations
                    else journey.fare_calculations[-1]
                )
                allowed = True
                return SupportRideEvidenceProjection(
                    ride_id=ride_id,
                    ride_request_id=ride.ride_request_id,
                    rider_reference=ride.rider_id,
                    driver_reference=ride.driver_id,
                    service_type=ride.service_type,
                    pickup_reference=ride.pickup_place_id,
                    destination_reference=ride.destination_place_id,
                    lifecycle_state=ride.state.value,
                    lifecycle_last_sequence=ride.last_sequence,
                    dispatch_handoff_id=ride.dispatch_handoff_id,
                    assignment_id=ride.assignment_id,
                    pricing_policy_version=None
                    if estimate is None
                    else estimate.policy_version,
                    fare_estimate_id=None if estimate is None else estimate.estimate_id,
                    estimate_acceptance_id=None
                    if handoff is None
                    else handoff.estimate_acceptance_id,
                    fare_calculation_id=None
                    if calculation is None
                    else calculation.calculation_id,
                    gross_fare_minor=None
                    if record is None
                    else record.financial_breakdown.gross_fare_minor,
                    payment_classification=None
                    if package is None
                    else package.payment_method.value,
                    cash_evidence_state=(
                        record.cash_evidence_state
                        if cash_evidence is None and record is not None
                        else None
                        if cash_evidence is None
                        else cash_evidence.state.value
                    ),
                    cash_accounting_state=None
                    if accounting is None
                    else accounting.state.value,
                    cash_reconciliation_state=None
                    if accounting is None
                    else accounting.reconciliation_state.value,
                    ledger_journal_id=None
                    if record is None
                    else record.ledger_journal_id,
                    rider_receipt_available=record is not None
                    and record.rider_receipt_id is not None,
                    driver_receipt_available=record is not None
                    and record.driver_receipt_id is not None,
                    completeness="complete" if not missing else "incomplete",
                    missing_authority=tuple(missing),
                )
        finally:
            self._audit.record(
                actor_identity_id=subject.identity_id,
                case_id=case_id,
                ride_id=ride_id,
                purpose=purpose,
                allowed=allowed,
                at=at,
            )
