"""Governed PRE-PRODUCTION certification of one authoritative cash ride.

This module contains synthetic test infrastructure only.  It deliberately uses a
NON_PRODUCTION accounting policy and must never be treated as Ethiopian legal,
tax, payment, or production-accounting approval.
"""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert

from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
    LifecycleCommandType,
)
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.models import (
    BookingConfirmation,
    BookingQuote,
    ProviderRouteEvidence,
    RoutePreview,
    TollEvidenceState,
    TrafficEvidenceState,
)
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.ledger.models import (
    LedgerAccount,
    LedgerAccountClass,
    LedgerBook,
    LedgerEntrySide,
)
from BACKEND.persistence.tables import ledger_accounts
from BACKEND.post_trip.application import (
    PostTripApplication,
    ReceiptPolicy,
    RideLedgerAccounts,
)
from BACKEND.post_trip.cash_accounting import (
    CashAccountingLedgerApplication,
    CashAccountingModel,
    CashAccountingPolicy,
    CashAccountingState,
    CashReconciliationApplication,
    CashReconciliationState,
    PolicyEnvironment,
    build_cash_reconciliation_evidence,
)
from BACKEND.post_trip.completion_pricing import PostTripCompletionPricingAdapter
from BACKEND.post_trip.models import EvidenceReference, PaymentMethod
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.models import PricingPolicy
from BACKEND.ride_request.application import (
    CreateRideRequestCommand,
    RideRequestApplication,
)
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    ServiceZone,
)
from BACKEND.support.models import SupportQueue
from BACKEND.support.ride_evidence import SupportRideEvidenceApplication
from BACKEND.support.service import SupportService
from tests.integration.test_active_ride_lifecycle_foundation import (
    subject as ride_subject,
)
from tests.integration.test_dispatch_handoff_localization import (
    NOW,
    POLICY,
    eligible_driver,
)
from tests.integration.test_pricing_foundation import route
from tests.integration.test_support_foundation import (
    grant,
    identity,
    subject,
    support_case,
)

pytestmark = pytest.mark.integration


class _CompletedMetrics:
    def completed_route_metrics(self, *, ride_id, route_evidence_id, at):
        del ride_id, route_evidence_id
        return route(at=at)


class _AuditSink:
    def __init__(self):
        self.events = []

    def record(self, **event):
        self.events.append(event)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _assigned_with_typed_booking(composition):
    """Create the canonical dispatch assignment with complete Booking evidence."""
    rider = identity(composition, IdentityType.RIDER)
    rider_subject = subject(rider)
    zone = ServiceZone(
        code=f"zone.{uuid4().hex}",
        version="zone.v1",
        min_latitude=8.5,
        max_latitude=9.5,
        min_longitude=38.2,
        max_longitude=39.2,
        supported_service_types=frozenset({"immediate_standard"}),
        active_from=NOW - timedelta(days=1),
        policy_version="zone.v1",
    )
    with composition.unit_of_work() as unit:
        unit.ride_requests.add_zone(zone)
    pickup = PickupDefinition(
        coordinate=Coordinate(latitude=9, longitude=38.7),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
        accuracy_metres=10,
        note="synthetic certification pickup",
        policy_version="pickup.v1",
    )
    destination = DestinationDefinition(
        coordinate=Coordinate(latitude=9.02, longitude=38.72),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
        accuracy_metres=10,
        note="synthetic certification destination",
    )
    request = RideRequestApplication(composition, POLICY).create(
        subject=rider_subject,
        command=CreateRideRequestCommand(
            client_request_id=uuid4(),
            idempotency_key=f"cash-certification-request-{rider.identity_id}",
            pickup=pickup,
            destination=destination,
            consent_policy_version="consent.v1",
        ),
        at=NOW,
    )
    with composition.unit_of_work() as unit:
        zone = unit.ride_requests.find_zone(latitude=9, longitude=38.7, at=NOW)
    assert zone is not None and zone.zone_id == request.service_zone_id

    pricing = PricingApplication(composition)
    makers = [identity(composition, IdentityType.STAFF) for _ in range(3)]
    operators = [subject(item) for item in makers]
    policy = pricing.create_policy(
        operators[0],
        PricingPolicy(
            policy_version=f"pricing.certification.{request.request_id.hex[:12]}",
            service_zone_id=request.service_zone_id,
            service_type="immediate_standard",
            currency="ETB",
            base_fare_minor=100,
            distance_rate_per_km_minor=10,
            time_rate_per_minute_minor=5,
            minimum_fare_minor=100,
            commission_basis_points=0,
            rounding_increment_minor=1,
            effective_from=NOW - timedelta(days=1),
            made_by_identity_id=operators[0].identity_id,
            created_at=NOW,
        ),
    )
    policy = pricing.approve_policy(operators[1], policy.policy_id, at=NOW)
    policy = pricing.publish_policy(operators[2], policy.policy_id, at=NOW)
    metrics = route(at=NOW)
    estimate = pricing.estimate(
        rider_subject,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=metrics,
        idempotency_key=f"cash-certification-estimate-{request.request_id}",
        correlation_id=request.request_id,
        causation_id=request.request_id,
        at=NOW,
    )
    acceptance = pricing.accept(
        rider_subject,
        estimate.estimate_id,
        idempotency_key=f"cash-certification-acceptance-{request.request_id}",
        at=NOW,
    )

    route_evidence = ProviderRouteEvidence(
        metrics=metrics,
        geometry=((9, 38.7), (9.02, 38.72)),
        origin_accuracy_metres=10,
        destination_accuracy_metres=10,
        map_confidence_bps=9500,
        traffic_state=TrafficEvidenceState.AVAILABLE,
        toll_state=TollEvidenceState.NONE_EVIDENCED,
        attribution="AYO synthetic certification route evidence",
    )
    quote = BookingQuote(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        breakdown=estimate.breakdown,
        expires_at=estimate.expires_at,
    )
    evidence_id = uuid4()
    session_hash = _digest(f"cash-certification-session-{request.request_id}")
    evidence_payload = "|".join(
        (
            str(evidence_id),
            session_hash,
            pickup.model_dump_json(),
            destination.model_dump_json(),
            route_evidence.model_dump_json(),
            quote.model_dump_json(),
            zone.version,
        )
    )
    preview = RoutePreview(
        evidence_id=evidence_id,
        booking_session_hash=session_hash,
        rider_identity_id=rider.identity_id,
        pickup=pickup,
        destination=destination,
        service_zone_id=request.service_zone_id,
        service_zone_version=zone.version,
        service_type="immediate_standard",
        route=route_evidence,
        quote=quote,
        evidence_hash=_digest(evidence_payload),
        created_at=NOW,
        expires_at=estimate.expires_at,
    )
    lineage_payload = ":".join(
        (
            str(request.request_id),
            str(estimate.estimate_id),
            str(acceptance.acceptance_id),
            str(estimate.policy_id),
            estimate.policy_version,
            str(acceptance.accepted_amount_minor),
            acceptance.currency,
        )
    )
    confirmation = BookingConfirmation(
        evidence_id=preview.evidence_id,
        evidence_hash=preview.evidence_hash,
        quote_id=preview.quote.quote_id,
        ride_request_id=request.request_id,
        fare_estimate_id=estimate.estimate_id,
        estimate_acceptance_id=acceptance.acceptance_id,
        pricing_lineage_hash=_digest(lineage_payload),
        rider_identity_id=rider.identity_id,
        idempotency_key_hash=_digest(f"cash-certification-{request.request_id}"),
        confirmed_at=NOW,
    )
    with composition.unit_of_work() as unit:
        unit.booking.add_preview(preview)
        unit.booking.add_confirmation(confirmation)
    with composition.unit_of_work() as unit:
        reloaded = unit.booking.get_preview(preview.evidence_id)
        stored_confirmation = unit.booking.get_confirmation_for_ride_request(
            request.request_id
        )
    assert reloaded == preview
    assert reloaded.service_zone_id == request.service_zone_id
    assert reloaded.quote.policy_id == estimate.policy_id
    assert reloaded.quote.policy_version == estimate.policy_version
    assert reloaded.quote.breakdown == estimate.breakdown
    assert stored_confirmation.evidence_id == reloaded.evidence_id
    assert stored_confirmation.evidence_hash == reloaded.evidence_hash
    assert stored_confirmation.quote_id == reloaded.quote.quote_id

    driver = eligible_driver(composition, 10)
    dispatch = ImmediateHandoffService(composition, policy_version="dispatch.v1")
    handoff = dispatch.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key=f"cash-certification-handoff-{request.request_id}",
        correlation_id=request.request_id,
        causation_id=confirmation.confirmation_id,
        at=NOW,
    )
    offer = dispatch.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer is not None
    assignment_id = dispatch.respond(
        offer_id=offer.offer_id,
        driver_id=driver.driver_id,
        expected_version=1,
        accept=True,
        idempotency_key=f"cash-certification-offer-{offer.offer_id}",
        at=NOW,
    )
    assert assignment_id is not None
    return (
        assignment_id,
        rider_subject,
        ride_subject(driver.driver_id, IdentityType.DRIVER),
    )


def _service(composition, *permissions: str) -> tuple[Identity, AuthorizationSubject]:
    value = identity(composition, IdentityType.SERVICE)
    for permission in permissions:
        grant(composition, value, permission)
    return value, subject(value)


def _ledger(composition, at):
    book = LedgerBook(
        code=f"cash.certification.{uuid4().hex}",
        description="Synthetic cash-ride certification ledger",
        base_currency="ETB",
        created_at=at,
    )
    definitions = (
        (
            "driver_remittance_receivable",
            LedgerAccountClass.ASSET,
            LedgerEntrySide.DEBIT,
        ),
        (
            "platform_service_fee_revenue",
            LedgerAccountClass.REVENUE,
            LedgerEntrySide.CREDIT,
        ),
        ("platform_cash_clearing", LedgerAccountClass.CLEARING, LedgerEntrySide.DEBIT),
    )
    accounts = {
        code: LedgerAccount(
            book_id=book.book_id,
            code=f"{code}.{uuid4().hex[:8]}",
            name=code.replace("_", " "),
            account_class=account_class,
            normal_side=side,
            currency="ETB",
            created_at=at,
        )
        for code, account_class, side in definitions
    }
    with composition.unit_of_work() as unit:
        unit.ledger.add_book(book)
        unit.connection.execute(
            insert(ledger_accounts),
            [account.model_dump() for account in accounts.values()],
        )
    return book, {code: account.account_id for code, account in accounts.items()}


def test_one_authoritative_immediate_standard_cash_ride(postgres_composition):
    """Certify the complete merged authority chain against real PostgreSQL."""
    assignment_id, rider, driver = _assigned_with_typed_booking(postgres_composition)
    lifecycle = ActiveRideLifecycleApplication(postgres_composition.unit_of_work)
    ride = lifecycle.start_from_assignment(assignment_id, now=NOW)
    with postgres_composition.unit_of_work() as unit:
        request = unit.ride_requests.get(ride.ride_request_id)
        confirmation = unit.booking.get_confirmation_for_ride_request(
            request.request_id
        )
        estimate = unit.pricing.get_estimate(confirmation.fare_estimate_id)
        acceptance = unit.pricing.get_acceptance_for_estimate(
            confirmation.fare_estimate_id
        )
        handoff = unit.handoff_dispatch.get_handoff(ride.dispatch_handoff_id)
        assert unit.identities.get(rider.identity_id).status is AccountStatus.ACTIVE
        assert unit.identities.get(driver.identity_id).status is AccountStatus.ACTIVE
    assert estimate is not None
    assert acceptance is not None
    assert estimate.ride_request_id == request.request_id
    assert estimate.rider_identity_id == rider.identity_id
    assert request.service_zone_id == estimate.service_zone_id
    assert acceptance.acceptance_id == confirmation.estimate_acceptance_id
    assert acceptance.estimate_id == estimate.estimate_id
    assert acceptance.rider_identity_id == rider.identity_id
    assert acceptance.accepted_policy_version == estimate.policy_version
    assert acceptance.currency == estimate.breakdown.currency
    assert acceptance.accepted_amount_minor == estimate.breakdown.rider_total_minor
    assert handoff.pricing_lineage_hash == confirmation.pricing_lineage_hash

    service_identity, service = _service(postgres_composition)
    transitions = (
        (driver, LifecycleCommandType.DRIVER_EN_ROUTE),
        (driver, LifecycleCommandType.DRIVER_ARRIVED),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (driver, LifecycleCommandType.RIDE_STARTED),
        (driver, LifecycleCommandType.DESTINATION_ARRIVED),
        (driver, LifecycleCommandType.RIDE_COMPLETED),
    )
    version = 1
    for actor, command_type in transitions:
        result = lifecycle.command(
            actor,
            ride.ride_id,
            LifecycleCommand(
                command_id=uuid4(),
                expected_version=version,
                command_type=command_type,
                reason_code=f"certification.{command_type.value}",
            ),
            now=NOW,
        )
        version = result["aggregate_version"]
    with postgres_composition.unit_of_work() as unit:
        completed = unit.active_rides.get(ride.ride_id)
    assert completed.state.value == "completed"

    pricing = PricingApplication(postgres_composition)
    pricing_adapter = PostTripCompletionPricingAdapter(
        postgres_composition, pricing, _CompletedMetrics(), service
    )
    post_trip = PostTripApplication(
        postgres_composition,
        pricing_adapter,
        RideLedgerAccounts(*(uuid4() for _ in range(8))),
        ReceiptPolicy(
            legal_entity="AYO SYNTHETIC CERTIFICATION ONLY",
            regulatory_policy_version="non-production.certification.v1",
            required_regulatory_information={"status": "NOT A TAX RECEIPT"},
        ),
    )
    route_reference = EvidenceReference(
        authority="synthetic.certification.route",
        reference_id=f"route-{ride.ride_id}",
        evidence_hash="a" * 64,
        summary={"distance_meters": 2000, "duration_seconds": 600},
    )
    record = post_trip.finalize(
        service,
        ride_id=ride.ride_id,
        route_reference=route_reference,
        payment_method=PaymentMethod.CASH,
        at=NOW,
    )
    record = post_trip.confirm_cash(
        rider,
        ride_id=ride.ride_id,
        confirmed=True,
        idempotency_key=f"cash-rider-{ride.ride_id}",
        at=NOW,
    )
    record = post_trip.confirm_cash(
        driver,
        ride_id=ride.ride_id,
        confirmed=True,
        idempotency_key=f"cash-driver-{ride.ride_id}",
        at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        evidence = unit.post_trip.cash_collection_evidence(ride.ride_id)
        calculation = unit.pricing.get_calculation(
            record.financial_breakdown.fare_calculation_id
        )
    assert evidence.state.value == "collection_corroborated"
    assert calculation.ride_id == ride.ride_id

    policy = CashAccountingPolicy(
        accounting_policy_version="non_production.certification_only.agent.v1",
        accounting_model=CashAccountingModel.AGENT_NET_REMITTANCE,
        currency="ETB",
        effective_from=NOW - timedelta(days=1),
        effective_until=NOW + timedelta(days=1),
        environment=PolicyEnvironment.NON_PRODUCTION,
        service_type="immediate_standard",
        payment_method="cash",
        platform_claim_basis_points=2000,
        driver_entitlement_basis_points=8000,
        tax_basis_points=0,
        principal_receivable_account=None,
        platform_claim_account="driver_remittance_receivable",
        driver_entitlement_account=None,
        platform_revenue_account="platform_service_fee_revenue",
        reconciliation_clearing_account="platform_cash_clearing",
        reconciliation_basis="synthetic.certification.manual_remittance",
        policy_evidence_hash="b" * 64,
        approval_reference="NON-PRODUCTION-CERTIFICATION-ONLY",
    )
    book, account_ids = _ledger(postgres_composition, NOW)
    with postgres_composition.unit_of_work() as unit:
        unit.post_trip.add_cash_accounting_policy(policy)
    accounting_app = CashAccountingLedgerApplication(
        postgres_composition,
        book_id=book.book_id,
        account_ids=account_ids,
        production=False,
    )
    accounting = accounting_app.post(
        service,
        ride_id=ride.ride_id,
        fare_calculation_id=calculation.calculation_id,
        evidence_id=evidence.evidence_id,
        accounting_policy_id=policy.accounting_policy_id,
        idempotency_key=f"cash-accounting-{ride.ride_id}",
        correlation_id=ride.ride_id,
        at=NOW,
    )
    replay = accounting_app.post(
        service,
        ride_id=ride.ride_id,
        fare_calculation_id=calculation.calculation_id,
        evidence_id=evidence.evidence_id,
        accounting_policy_id=policy.accounting_policy_id,
        idempotency_key=f"cash-accounting-{ride.ride_id}",
        correlation_id=ride.ride_id,
        at=NOW,
    )
    assert replay == accounting
    assert accounting.state is CashAccountingState.ACCOUNTING_POSTED
    assert evidence.gross_cash_reported_minor != accounting.platform_claim_minor

    grant(postgres_composition, service_identity, "cash.reconciliation.execute")
    reconciliation_evidence = build_cash_reconciliation_evidence(
        reconciliation_evidence_id=uuid4(),
        ride_id=ride.ride_id,
        accounting_instruction_id=accounting.instruction_id,
        accounting_policy_id=policy.accounting_policy_id,
        accounting_policy_version=policy.accounting_policy_version,
        original_accounting_journal_id=accounting.ledger_journal_id,
        platform_claim_minor=accounting.platform_claim_minor,
        currency="ETB",
        evidence_type="manual_remittance",
        source_classification="synthetic_certification",
        authorized_actor_id=service.identity_id,
        occurred_at=NOW,
        correlation_id=ride.ride_id,
        causation_id=accounting.instruction_id,
    )
    reconciliation = CashReconciliationApplication(
        postgres_composition,
        book_id=book.book_id,
        account_ids=account_ids,
        production=False,
    ).clear(
        service,
        evidence=reconciliation_evidence,
        idempotency_key=f"cash-reconciliation-{ride.ride_id}",
        expected_version=accounting.version,
    )
    assert reconciliation.reconciliation_state is CashReconciliationState.CLEARED
    assert reconciliation.clearing_journal_id != reconciliation.ledger_journal_id

    receipt_record = post_trip.issue_cash_accounting_receipts(
        service, ride_id=ride.ride_id, at=NOW
    )
    assert receipt_record.rider_receipt_id and receipt_record.driver_receipt_id
    assert post_trip.summary(rider, ride_id=ride.ride_id)["receipts"]
    assert post_trip.summary(driver, ride_id=ride.ride_id)["receipts"]

    support_staff = identity(postgres_composition, IdentityType.STAFF)
    grant(postgres_composition, support_staff, "support.trip.read_limited")
    grant(postgres_composition, support_staff, "support.queue.general.access")
    case = support_case(
        identity(postgres_composition, IdentityType.RIDER),
        assigned_queue=SupportQueue.GENERAL,
        related_ride_reference=str(ride.ride_id),
    )
    with postgres_composition.unit_of_work() as unit:
        SupportService().create_case(unit, case, actor=None)
    audit = _AuditSink()
    projection = SupportRideEvidenceApplication(postgres_composition, audit).project(
        subject=subject(support_staff),
        case_id=case.case_id,
        ride_id=ride.ride_id,
        purpose="ride_cash_certification",
        step_up_verified=False,
        at=NOW,
    )
    assert projection.completeness == "complete"
    assert projection.cash_accounting_journal_id == accounting.ledger_journal_id
    assert (
        projection.cash_reconciliation_journal_id == reconciliation.clearing_journal_id
    )
    assert audit.events[-1]["allowed"] is True
