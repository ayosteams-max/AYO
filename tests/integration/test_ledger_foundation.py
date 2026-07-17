from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert as sa_insert

from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
    LifecycleCommandType,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import IdentityType
from BACKEND.ledger.engine import LedgerConflict, deterministic_replay_view
from BACKEND.ledger.models import (
    LedgerAccount,
    LedgerAccountClass,
    LedgerBook,
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.persistence.tables import ledger_accounts
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.models import DataQuality, PricingPolicy, RouteMetrics
from tests.integration.test_dispatch_handoff_localization import (
    eligible_driver,
    ready_request,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, tzinfo=UTC)


def subject(identity_type: IdentityType, identity_id: UUID | None = None):
    return AuthorizationSubject(
        identity_id=identity_id or uuid4(),
        identity_type=identity_type,
        actor_type={
            IdentityType.RIDER: ActorType.RIDER,
            IdentityType.DRIVER: ActorType.DRIVER,
            IdentityType.STAFF: ActorType.STAFF,
            IdentityType.SERVICE: ActorType.SERVICE,
        }[identity_type],
    )


def route(distance=7000, duration=1200, at=NOW):
    return RouteMetrics(
        distance_meters=distance,
        duration_seconds=duration,
        observed_at=at,
        provider_id="synthetic.route",
        provider_version="v1",
        distance_source="approved_route_metric",
        duration_source="approved_route_metric",
        provenance_reference=f"approved-{uuid4()}",
        data_quality=DataQuality.APPROVED_SYNTHETIC,
    )


def published_policy(app, zone_id):
    maker, checker, publisher = (
        subject(IdentityType.STAFF),
        subject(IdentityType.STAFF),
        subject(IdentityType.STAFF),
    )
    item = PricingPolicy(
        policy_version=f"synthetic.{uuid4().hex}",
        service_zone_id=zone_id,
        service_type="immediate_standard",
        currency="ETB",
        base_fare_minor=1200,
        distance_rate_per_km_minor=450,
        time_rate_per_minute_minor=150,
        minimum_fare_minor=1500,
        commission_basis_points=2000,
        tax_placeholder_basis_points=0,
        rounding_increment_minor=5,
        effective_from=NOW - timedelta(days=1),
        made_by_identity_id=maker.identity_id,
        created_at=NOW,
    )
    app.create_policy(maker, item)
    app.approve_policy(checker, item.policy_id, at=NOW)
    return app.publish_policy(publisher, item.policy_id, at=NOW)


def completed_ride(composition, request):
    driver = eligible_driver(composition, 10)
    dispatch = ImmediateHandoffService(composition, policy_version="dispatch.v1")
    handoff = dispatch.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key=f"handoff-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = dispatch.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer is not None
    assignment_id = dispatch.respond(
        offer_id=offer.offer_id,
        driver_id=driver.driver_id,
        expected_version=1,
        accept=True,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    assert assignment_id is not None
    lifecycle = ActiveRideLifecycleApplication(composition.unit_of_work)
    ride = lifecycle.start_from_assignment(assignment_id, now=NOW)
    service = subject(IdentityType.SERVICE)
    actor = subject(IdentityType.DRIVER, driver.driver_id)
    steps = (
        (actor, LifecycleCommandType.DRIVER_EN_ROUTE),
        (actor, LifecycleCommandType.DRIVER_ARRIVED),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (actor, LifecycleCommandType.RIDE_STARTED),
        (actor, LifecycleCommandType.DESTINATION_ARRIVED),
        (actor, LifecycleCommandType.RIDE_COMPLETED),
    )
    version = 1
    for who, kind in steps:
        result = lifecycle.command(
            who,
            ride.ride_id,
            LifecycleCommand(
                command_id=uuid4(),
                expected_version=version,
                command_type=kind,
                reason_code=f"test.{kind.value}",
            ),
            now=NOW,
        )
        version = result["aggregate_version"]
    return ride, driver


def test_ledger_posting_is_append_only_balanced_idempotent(postgres_composition):
    request, rider = ready_request(postgres_composition)
    pricing = PricingApplication(postgres_composition)
    policy = published_policy(pricing, request.service_zone_id)
    estimate = pricing.estimate(
        rider,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    pricing.accept(
        rider,
        estimate.estimate_id,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    ride, driver = completed_ride(postgres_composition, request)
    calculation = pricing.final_calculation(
        subject(IdentityType.SERVICE),
        ride_id=ride.ride_id,
        estimate_id=estimate.estimate_id,
        metrics=route(distance=7100),
        idempotency_key=f"final-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )

    with postgres_composition.unit_of_work() as unit:
        book = unit.ledger.add_book(
            LedgerBook(
                code=f"rides.etb.{uuid4().hex[:12]}",
                description="Ride financial postings in ETB",
                base_currency="ETB",
                created_at=NOW,
            )
        )
        rider_ar = LedgerAccount(
            book_id=book.book_id,
            code=f"rider.ar.{uuid4().hex[:8]}",
            name="Rider Receivable",
            account_class=LedgerAccountClass.ASSET,
            normal_side=LedgerEntrySide.DEBIT,
            currency="ETB",
            created_at=NOW,
        )
        revenue = LedgerAccount(
            book_id=book.book_id,
            code=f"ayo.revenue.{uuid4().hex[:8]}",
            name="AYO Fare Revenue",
            account_class=LedgerAccountClass.REVENUE,
            normal_side=LedgerEntrySide.CREDIT,
            currency="ETB",
            created_at=NOW,
        )
        unit.connection.execute(
            # Repository account-creation API is deferred; direct insert keeps this test scoped.
            sa_insert(ledger_accounts),
            [rider_ar.model_dump(), revenue.model_dump()],
        )

        key = f"ledger-post-{uuid4()}"
        reserve = unit.ledger.reserve_idempotency(
            actor_id=rider.identity_id,
            operation="post_journal",
            key=key,
            payload={
                "fare_calculation_id": str(calculation.calculation_id),
                "rider_total_minor": calculation.breakdown.rider_total_minor,
            },
            response_reference=uuid4(),
            at=NOW,
        )

        trace = LedgerTraceability(
            ride_request_id=calculation.financial_traceability.ride_request_id,
            dispatch_handoff_id=calculation.financial_traceability.dispatch_handoff_id,
            assignment_id=calculation.financial_traceability.assignment_id,
            active_ride_id=calculation.financial_traceability.active_ride_id,
            fare_estimate_id=calculation.financial_traceability.fare_estimate_id,
            fare_calculation_id=calculation.financial_traceability.fare_calculation_id,
        )
        journal = LedgerJournal(
            journal_id=reserve,
            book_id=book.book_id,
            business_event_type="pricing.final_calculated",
            business_event_id=calculation.calculation_id,
            operation="post_journal",
            idempotency_key=key,
            actor_identity_id=rider.identity_id,
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=trace,
            entries=(
                LedgerEntry(
                    account_id=rider_ar.account_id,
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=calculation.breakdown.rider_total_minor,
                    currency="ETB",
                    line_index=1,
                ),
                LedgerEntry(
                    account_id=revenue.account_id,
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=calculation.breakdown.rider_total_minor,
                    currency="ETB",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=calculation.calculation_id,
            audit_reference=uuid4(),
        )
        posted = unit.ledger.post_journal(journal)
        replay = deterministic_replay_view(posted)
        assert replay["traceability"]["fare_calculation_id"] == str(
            calculation.calculation_id
        )
        assert unit.ledger.get_journal(posted.journal_id) is not None
        assert (
            unit.ledger.account_balance(rider_ar.account_id, "ETB").net_minor
            == calculation.breakdown.rider_total_minor
        )
        assert (
            unit.ledger.account_balance(revenue.account_id, "ETB").net_minor
            == -calculation.breakdown.rider_total_minor
        )

        same = unit.ledger.reserve_idempotency(
            actor_id=rider.identity_id,
            operation="post_journal",
            key=key,
            payload={
                "fare_calculation_id": str(calculation.calculation_id),
                "rider_total_minor": calculation.breakdown.rider_total_minor,
            },
            response_reference=uuid4(),
            at=NOW,
        )
        assert same == reserve

        with pytest.raises(LedgerConflict, match="idempotency_conflict"):
            unit.ledger.reserve_idempotency(
                actor_id=rider.identity_id,
                operation="post_journal",
                key=key,
                payload={
                    "fare_calculation_id": str(calculation.calculation_id),
                    "rider_total_minor": calculation.breakdown.rider_total_minor + 1,
                },
                response_reference=uuid4(),
                at=NOW,
            )


def test_ledger_traceability_fails_closed_for_forged_lineage(postgres_composition):
    request, rider = ready_request(postgres_composition)
    pricing = PricingApplication(postgres_composition)
    policy = published_policy(pricing, request.service_zone_id)
    estimate = pricing.estimate(
        rider,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    pricing.accept(
        rider,
        estimate.estimate_id,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    ride, _ = completed_ride(postgres_composition, request)
    calculation = pricing.final_calculation(
        subject(IdentityType.SERVICE),
        ride_id=ride.ride_id,
        estimate_id=estimate.estimate_id,
        metrics=route(distance=7300),
        idempotency_key=f"final-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )

    with postgres_composition.unit_of_work() as unit:
        book = unit.ledger.add_book(
            LedgerBook(
                code=f"rides.etb.{uuid4().hex[:12]}",
                description="Ride financial postings in ETB",
                base_currency="ETB",
                created_at=NOW,
            )
        )
        bogus_account = LedgerAccount(
            book_id=book.book_id,
            code=f"bogus.{uuid4().hex[:8]}",
            name="Bogus",
            account_class=LedgerAccountClass.ASSET,
            normal_side=LedgerEntrySide.DEBIT,
            currency="ETB",
            created_at=NOW,
        )
        unit.connection.execute(
            sa_insert(ledger_accounts),
            [bogus_account.model_dump()],
        )
        journal = LedgerJournal(
            book_id=book.book_id,
            business_event_type="pricing.final_calculated",
            business_event_id=calculation.calculation_id,
            operation="post_journal",
            idempotency_key=f"ledger-{uuid4()}",
            actor_identity_id=rider.identity_id,
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=LedgerTraceability(
                ride_request_id=uuid4(),
                dispatch_handoff_id=calculation.financial_traceability.dispatch_handoff_id,
                assignment_id=calculation.financial_traceability.assignment_id,
                active_ride_id=calculation.financial_traceability.active_ride_id,
                fare_estimate_id=calculation.financial_traceability.fare_estimate_id,
                fare_calculation_id=calculation.financial_traceability.fare_calculation_id,
            ),
            entries=(
                LedgerEntry(
                    account_id=bogus_account.account_id,
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=1,
                ),
                LedgerEntry(
                    account_id=bogus_account.account_id,
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=calculation.calculation_id,
            audit_reference=uuid4(),
        )
        with pytest.raises(LedgerConflict, match="ledger_traceability_conflict"):
            unit.ledger.post_journal(journal)
