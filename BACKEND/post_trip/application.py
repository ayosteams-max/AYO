from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from BACKEND.active_ride.models import ActiveRideState
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.ledger.models import (
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.post_trip.engine import (
    PostTripConflict,
    assert_rating_allowed,
    assert_settlement_ready,
    canonical_hash,
    cash_state,
    finalize_package,
)
from BACKEND.post_trip.models import (
    CashConfirmation,
    FinancialBreakdown,
    PaymentMethod,
    PostTripRecord,
    PreferenceSignal,
    Rating,
    Receipt,
)
from BACKEND.wallet.application import WalletOrchestrationService
from BACKEND.wallet.models import WalletAuthoritativeSourceType, WalletEntryType


class CompletionPricingAuthority(Protocol):
    def final_breakdown(
        self,
        *,
        ride_id: UUID,
        booking_evidence_id: UUID,
        route_evidence_id: str,
        at: datetime,
    ) -> FinancialBreakdown: ...


@dataclass(frozen=True, slots=True)
class RideLedgerAccounts:
    book_id: UUID
    settlement_clearing: UUID
    driver_earnings_payable: UUID
    commission_revenue: UUID
    tax_payable: UUID
    incentive_expense: UUID
    adjustment_expense: UUID
    adjustment_recovery: UUID


@dataclass(frozen=True, slots=True)
class ReceiptPolicy:
    legal_entity: str
    regulatory_policy_version: str
    required_regulatory_information: dict[str, str]


class PostTripApplication:
    def __init__(
        self,
        composition,
        pricing: CompletionPricingAuthority,
        accounts: RideLedgerAccounts,
        receipt_policy: ReceiptPolicy,
    ) -> None:
        if not receipt_policy.required_regulatory_information:
            raise ValueError("Receipt regulatory information is required")
        self._composition = composition
        self._pricing = pricing
        self._accounts = accounts
        self._receipt_policy = receipt_policy
        self._wallets = WalletOrchestrationService(composition)

    def summary(
        self, subject: AuthorizationSubject, *, ride_id: UUID
    ) -> dict[str, Any]:
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id)
            record = unit.post_trip.get(ride_id)
            package = unit.post_trip.package_for_ride(ride_id)
            if (
                ride is None
                or record is None
                or package is None
                or subject.identity_id not in {ride.rider_id, ride.driver_id}
            ):
                raise PostTripConflict("post_trip_not_found")
            receipts = unit.post_trip.receipts_for(ride_id, subject.identity_id)
            return {
                "ride_id": str(ride_id),
                "participant_role": "rider"
                if subject.identity_id == ride.rider_id
                else "driver",
                "state": record.state.value,
                "cash_state": None
                if record.cash_state is None
                else record.cash_state.value,
                "pickup": ride.pickup_place_id,
                "destination": ride.destination_place_id,
                "distance_meters": package.route.summary.get("distance_meters"),
                "duration_seconds": package.route.summary.get("duration_seconds"),
                "fare": record.financial_breakdown.model_dump(mode="json"),
                "payment_method": package.payment_method.value,
                "timeline_sequence": ride.last_sequence,
                "receipts": [item.model_dump(mode="json") for item in receipts],
                "rating_window_expires_at": (
                    ride.updated_at + timedelta(hours=72)
                ).isoformat(),
            }

    def finalize(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        route_reference,
        payment_method: PaymentMethod,
        payment_reference=None,
        at: datetime,
    ) -> PostTripRecord:
        self._service(subject)
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id, lock=True)
            if (
                ride is None
                or ride.state is not ActiveRideState.COMPLETED
                or ride.driver_id is None
                or ride.vehicle_id is None
                or ride.ride_request_id is None
                or ride.dispatch_handoff_id is None
                or ride.assignment_id is None
            ):
                raise PostTripConflict("completed_canonical_ride_required")
            confirmation = unit.booking.get_confirmation_for_ride_request(
                ride.ride_request_id
            )
            if confirmation is None:
                raise PostTripConflict("booking_evidence_missing")
            preview = unit.booking.get_preview(confirmation.evidence_id)
            if preview is None:
                raise PostTripConflict("booking_evidence_missing")
        breakdown = self._pricing.final_breakdown(
            ride_id=ride_id,
            booking_evidence_id=confirmation.evidence_id,
            route_evidence_id=route_reference.reference_id,
            at=at,
        )
        values = dict(
            ride_id=ride_id,
            rider_identity_id=ride.rider_id,
            driver_identity_id=ride.driver_id,
            vehicle_id=ride.vehicle_id,
            payment_method=payment_method,
            booking=route_reference.model_copy(
                update={
                    "authority": "booking",
                    "reference_id": str(confirmation.evidence_id),
                    "evidence_hash": confirmation.evidence_hash,
                }
            ),
            route=route_reference,
            pricing=route_reference.model_copy(
                update={
                    "authority": "pricing",
                    "reference_id": str(breakdown.fare_calculation_id),
                    "evidence_hash": breakdown.policy_evidence_hash,
                }
            ),
            dispatch=route_reference.model_copy(
                update={
                    "authority": "dispatch",
                    "reference_id": str(ride.dispatch_handoff_id),
                }
            ),
            assignment=route_reference.model_copy(
                update={
                    "authority": "assignment",
                    "reference_id": str(ride.assignment_id),
                }
            ),
            timeline=route_reference.model_copy(
                update={
                    "authority": "active_ride.timeline",
                    "reference_id": str(ride_id),
                    "evidence_hash": canonical_hash(
                        {"last_sequence": ride.last_sequence, "version": ride.version}
                    ),
                }
            ),
            completion=route_reference.model_copy(
                update={
                    "authority": "active_ride.completion",
                    "reference_id": str(ride_id),
                    "evidence_hash": canonical_hash(
                        {"state": ride.state.value, "updated_at": ride.updated_at}
                    ),
                }
            ),
            payment=payment_reference,
        )
        package = finalize_package(values=values, finalized_at=at)
        with self._composition.unit_of_work() as unit:
            existed = unit.post_trip.package_for_ride(ride_id) is not None
            record = unit.post_trip.create_package(package, breakdown)
            if not existed:
                unit.post_trip.notification_intent(
                    ride_id=ride_id,
                    event_type="trip.completed",
                    recipient_identity_id=ride.rider_id,
                    payload={"ride_id": str(ride_id)},
                    at=at,
                )
                unit.post_trip.notification_intent(
                    ride_id=ride_id,
                    event_type="trip.completed",
                    recipient_identity_id=ride.driver_id,
                    payload={"ride_id": str(ride_id)},
                    at=at,
                )
            return record

    def confirm_cash(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        confirmed: bool,
        idempotency_key: str,
        at: datetime,
    ) -> PostTripRecord:
        if not 16 <= len(idempotency_key) <= 128:
            raise PostTripConflict("idempotency_key_invalid")
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id)
            record = unit.post_trip.get(ride_id, lock=True)
            if ride is None or record is None or record.cash_state is None:
                raise PostTripConflict("cash_confirmation_unavailable")
            if (
                subject.identity_type is IdentityType.RIDER
                and subject.identity_id == ride.rider_id
            ):
                role = "rider"
            elif (
                subject.identity_type is IdentityType.DRIVER
                and subject.identity_id == ride.driver_id
            ):
                role = "driver"
            else:
                raise PostTripConflict("access_denied")
            confirmations, created = unit.post_trip.add_cash_confirmation(
                CashConfirmation(
                    ride_id=ride_id,
                    actor_identity_id=subject.identity_id,
                    actor_role=role,
                    confirmed=confirmed,
                    idempotency_key_hash=canonical_hash(idempotency_key),
                    recorded_at=at,
                )
            )
            if not created:
                return record
            updated = unit.post_trip.update_cash_state(
                ride_id, cash_state(confirmations).value, record.version
            )
            if updated.cash_state is not None and updated.cash_state.value in {
                "cash_settled",
                "cash_settlement_review",
            }:
                unit.post_trip.notification_intent(
                    ride_id=ride_id,
                    event_type=f"trip.{updated.cash_state.value}",
                    recipient_identity_id=ride.rider_id,
                    payload={"ride_id": str(ride_id)},
                    at=at,
                )
                unit.post_trip.notification_intent(
                    ride_id=ride_id,
                    event_type=f"trip.{updated.cash_state.value}",
                    recipient_identity_id=ride.driver_id,
                    payload={"ride_id": str(ride_id)},
                    at=at,
                )
            return updated

    def rate(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        stars: int,
        feedback: str | None,
        prefer_driver: bool,
        at: datetime,
    ) -> Rating:
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id)
            if (
                ride is None
                or ride.state is not ActiveRideState.COMPLETED
                or ride.driver_id is None
            ):
                raise PostTripConflict("completed_canonical_ride_required")
            if (
                subject.identity_type is IdentityType.RIDER
                and subject.identity_id == ride.rider_id
            ):
                target, can_prefer = ride.driver_id, True
            elif (
                subject.identity_type is IdentityType.DRIVER
                and subject.identity_id == ride.driver_id
            ):
                target, can_prefer = ride.rider_id, False
            else:
                raise PostTripConflict("access_denied")
            expires = assert_rating_allowed(
                completed_at=ride.updated_at, submitted_at=at
            )
            rating = unit.post_trip.add_rating(
                Rating(
                    ride_id=ride_id,
                    author_identity_id=subject.identity_id,
                    target_identity_id=target,
                    stars=stars,
                    feedback=feedback,
                    preference_requested=prefer_driver,
                    submitted_at=at,
                    window_expires_at=expires,
                )
            )
            if prefer_driver:
                if not can_prefer:
                    raise PostTripConflict("preference_not_available")
                unit.post_trip.upsert_preference(
                    PreferenceSignal(
                        owner_identity_id=ride.rider_id,
                        capability="ride",
                        target_type="driver",
                        target_identity_id=ride.driver_id,
                        source_ride_id=ride_id,
                        created_at=at,
                    )
                )
            return rating

    def settle(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> PostTripRecord:
        self._service(subject)
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id)
            record = unit.post_trip.get(ride_id, lock=True)
            package = unit.post_trip.package_for_ride(ride_id)
            if (
                ride is None
                or record is None
                or package is None
                or ride.driver_id is None
                or ride.ride_request_id is None
                or ride.dispatch_handoff_id is None
                or ride.assignment_id is None
            ):
                raise PostTripConflict("post_trip_not_ready")
            if record.state.value in {"settled", "archived"}:
                return record
            assert_settlement_ready(package.payment_method, record.cash_state)
            b = record.financial_breakdown
            entries = self._entries(b)
            journal = unit.ledger.post_journal(
                LedgerJournal(
                    book_id=self._accounts.book_id,
                    business_event_type="ride.settlement",
                    business_event_id=ride_id,
                    operation="ride.settlement.post",
                    idempotency_key=idempotency_key,
                    actor_identity_id=subject.identity_id,
                    source_system="post_trip",
                    reason_code="ride.completed.settlement",
                    traceability=LedgerTraceability(
                        ride_request_id=ride.ride_request_id,
                        dispatch_handoff_id=ride.dispatch_handoff_id,
                        assignment_id=ride.assignment_id,
                        active_ride_id=ride_id,
                        fare_estimate_id=record.financial_breakdown.fare_estimate_id,
                        fare_calculation_id=record.financial_breakdown.fare_calculation_id,
                    ),
                    entries=entries,
                    effective_at=at,
                    recorded_at=at,
                    correlation_id=correlation_id,
                    causation_id=record.package_id,
                    audit_reference=uuid4(),
                )
            )
            wallet_entry_id = None
            if package.payment_method is PaymentMethod.LICENSED_DIGITAL_PROVIDER:
                self._wallets.consume_authoritative_event_with_unit(
                    unit,
                    subject,
                    owner_identity_id=ride.driver_id,
                    authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
                    authoritative_source_id=journal.journal_id,
                    entry_type=WalletEntryType.AVAILABLE_CREDIT,
                    amount_minor=b.net_driver_earnings_minor,
                    reason_code="wallet.transfer_in.ayo_ride",
                    idempotency_key=f"wallet:{idempotency_key}",
                    correlation_id=correlation_id,
                    causation_id=journal.journal_id,
                    at=at,
                )
                lineage = unit.wallets.list_lineage(
                    unit.wallets.get_account_by_owner(ride.driver_id).wallet_account_id
                )
                wallet_entry_id = lineage[-1].wallet_entry_id
            rider_receipt = unit.post_trip.add_receipt(
                self._receipt(ride, record, "rider_receipt", ride.rider_id, at)
            )
            driver_receipt = unit.post_trip.add_receipt(
                self._receipt(
                    ride, record, "driver_settlement_summary", ride.driver_id, at
                )
            )
            settled = unit.post_trip.mark_settled(
                ride_id,
                journal_id=journal.journal_id,
                wallet_entry_id=wallet_entry_id,
                rider_receipt_id=rider_receipt.receipt_id,
                driver_receipt_id=driver_receipt.receipt_id,
                expected_version=record.version,
            )
            unit.post_trip.notification_intent(
                ride_id=ride_id,
                event_type="ride.earnings_settled",
                recipient_identity_id=ride.driver_id,
                payload={"ride_id": str(ride_id), "currency": "ETB"},
                at=at,
            )
            unit.post_trip.notification_intent(
                ride_id=ride_id,
                event_type="ride.receipt_available",
                recipient_identity_id=ride.rider_id,
                payload={
                    "ride_id": str(ride_id),
                    "receipt_id": str(rider_receipt.receipt_id),
                },
                at=at,
            )
            return unit.post_trip.archive(
                ride_id, at=at, expected_version=settled.version
            )

    def _entries(self, b: FinancialBreakdown) -> tuple[LedgerEntry, ...]:
        debit_total = (
            b.gross_fare_minor + b.incentives_minor + max(b.adjustments_minor, 0)
        )
        values = [
            (
                self._accounts.settlement_clearing,
                LedgerEntrySide.DEBIT,
                b.gross_fare_minor,
            ),
            (
                self._accounts.driver_earnings_payable,
                LedgerEntrySide.CREDIT,
                b.net_driver_earnings_minor,
            ),
            (
                self._accounts.commission_revenue,
                LedgerEntrySide.CREDIT,
                b.commission_minor,
            ),
            (self._accounts.tax_payable, LedgerEntrySide.CREDIT, b.taxes_minor),
        ]
        if b.incentives_minor:
            values.append(
                (
                    self._accounts.incentive_expense,
                    LedgerEntrySide.DEBIT,
                    b.incentives_minor,
                )
            )
        if b.adjustments_minor > 0:
            values.append(
                (
                    self._accounts.adjustment_expense,
                    LedgerEntrySide.DEBIT,
                    b.adjustments_minor,
                )
            )
        if b.adjustments_minor < 0:
            values.append(
                (
                    self._accounts.adjustment_recovery,
                    LedgerEntrySide.CREDIT,
                    -b.adjustments_minor,
                )
            )
        values = [item for item in values if item[2] > 0]
        if sum(
            v for _, side, v in values if side is LedgerEntrySide.DEBIT
        ) != debit_total or sum(
            v for _, side, v in values if side is LedgerEntrySide.DEBIT
        ) != sum(v for _, side, v in values if side is LedgerEntrySide.CREDIT):
            raise PostTripConflict("settlement_not_balanced")
        return tuple(
            LedgerEntry(
                account_id=account,
                side=side,
                amount_minor=amount,
                currency="ETB",
                line_index=index,
            )
            for index, (account, side, amount) in enumerate(values, 1)
        )

    def _receipt(
        self, ride: Any, record: PostTripRecord, kind: str, owner: UUID, at: datetime
    ) -> Receipt:
        payload = {
            "trip_id": str(ride.ride_id),
            "date": at.date().isoformat(),
            "time": at.time().isoformat(),
            "pickup": ride.pickup_place_id,
            "destination": ride.destination_place_id,
            "fare_breakdown": record.financial_breakdown.model_dump(mode="json"),
            "payment_method": "cash"
            if record.cash_state is not None
            else "licensed_digital_provider",
            "legal_entity": self._receipt_policy.legal_entity,
            "regulatory_information": self._receipt_policy.required_regulatory_information,
        }
        return Receipt(
            receipt_number=f"AYO-RIDE-{str(ride.ride_id).replace('-', '').upper()[:16]}-{'R' if kind == 'rider_receipt' else 'D'}",
            ride_id=ride.ride_id,
            issued_to_identity_id=owner,
            receipt_type=kind,
            payload=payload,
            payload_hash=canonical_hash(payload),
            legal_entity=self._receipt_policy.legal_entity,
            regulatory_policy_version=self._receipt_policy.regulatory_policy_version,
            issued_at=at,
        )

    @staticmethod
    def _service(subject: AuthorizationSubject) -> None:
        if subject.identity_type is not IdentityType.SERVICE:
            raise PostTripConflict("access_denied")
