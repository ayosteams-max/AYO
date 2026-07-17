from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
    LifecycleCommandType,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.persistence.pricing_repository import PostgresPricingRepository
from BACKEND.persistence.tables import (
    fare_calculations,
    fare_estimates,
    pricing_events,
    pricing_outbox,
)
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.engine import PricingConflict, reconstruct
from BACKEND.pricing.models import (
    DataQuality,
    FinancialTraceability,
    PricingPolicy,
    RouteMetrics,
)
from tests.integration.test_active_ride_lifecycle_foundation import assigned
from tests.integration.test_dispatch_handoff_localization import (
    eligible_driver,
    ready_request,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, tzinfo=UTC)


def subject(
    identity_id_or_type: UUID | IdentityType | None,
    identity_type: IdentityType | None = None,
):
    if isinstance(identity_id_or_type, IdentityType):
        identity_type = identity_id_or_type
        identity_id = None
    else:
        identity_id = identity_id_or_type
    if identity_type is None:
        raise TypeError("identity_type is required")
    actor = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.DRIVER: ActorType.DRIVER,
        IdentityType.STAFF: ActorType.STAFF,
        IdentityType.SERVICE: ActorType.SERVICE,
    }[identity_type]
    return AuthorizationSubject(
        identity_id=identity_id or uuid4(),
        identity_type=identity_type,
        actor_type=actor,
    )


def route(distance=5000, duration=900, at=NOW):
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


def grant_trace_read(postgres_composition, reviewer: AuthorizationSubject) -> None:
    permission = Permission(
        code="pricing.trace.read",
        description="Read test financial trace.",
        created_at=NOW,
    )
    role = Role(
        code=f"finance.trace.{uuid4().hex[:8]}",
        description="Test financial trace role.",
        created_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        unit.identities.create(
            Identity(
                identity_id=reviewer.identity_id,
                identity_type=reviewer.identity_type,
                status=AccountStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        unit.authorization.create_permission(permission)
        unit.authorization.create_role(role)
        unit.authorization.grant_permission(role.role_id, permission.permission_id)
        unit.authorization.assign_role(
            RoleAssignment(
                identity_id=reviewer.identity_id,
                role_id=role.role_id,
                assigned_by_identity_id=reviewer.identity_id,
                assigned_at=NOW,
            )
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
        base_fare_minor=1000,
        distance_rate_per_km_minor=500,
        time_rate_per_minute_minor=200,
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


def estimate_and_accept(composition):
    request, rider = ready_request(composition)
    app = PricingApplication(composition)
    policy = published_policy(app, request.service_zone_id)
    estimate = app.estimate(
        rider,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    acceptance = app.accept(
        rider,
        estimate.estimate_id,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    return app, request, rider, estimate, acceptance


def complete_ride(composition):
    assignment_id, rider, driver = assigned(composition)
    lifecycle = ActiveRideLifecycleApplication(composition.unit_of_work)
    ride = lifecycle.start_from_assignment(assignment_id, now=NOW)
    service = subject(IdentityType.SERVICE)
    steps = (
        (driver, LifecycleCommandType.DRIVER_EN_ROUTE),
        (driver, LifecycleCommandType.DRIVER_ARRIVED),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (driver, LifecycleCommandType.RIDE_STARTED),
        (driver, LifecycleCommandType.DESTINATION_ARRIVED),
        (driver, LifecycleCommandType.RIDE_COMPLETED),
    )
    version = 1
    for actor, kind in steps:
        result = lifecycle.command(
            actor,
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
    return ride, rider, driver


def complete_request_ride(composition, request):
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
    steps = (
        (
            subject(driver.driver_id, IdentityType.DRIVER),
            LifecycleCommandType.DRIVER_EN_ROUTE,
        ),
        (
            subject(driver.driver_id, IdentityType.DRIVER),
            LifecycleCommandType.DRIVER_ARRIVED,
        ),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (
            subject(driver.driver_id, IdentityType.DRIVER),
            LifecycleCommandType.RIDE_STARTED,
        ),
        (
            subject(driver.driver_id, IdentityType.DRIVER),
            LifecycleCommandType.DESTINATION_ARRIVED,
        ),
        (
            subject(driver.driver_id, IdentityType.DRIVER),
            LifecycleCommandType.RIDE_COMPLETED,
        ),
    )
    version = 1
    for actor, kind in steps:
        result = lifecycle.command(
            actor,
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
    return ride


def test_financial_traceability_fails_closed_for_missing_or_conflicting_chain() -> None:
    ride_request_id = uuid4()
    estimate_id = uuid4()
    with pytest.raises(ValidationError):
        FinancialTraceability(
            ride_request_id=ride_request_id,
            fare_estimate_id=estimate_id,
            active_ride_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        FinancialTraceability(
            ride_request_id=ride_request_id,
            dispatch_handoff_id=uuid4(),
            assignment_id=uuid4(),
            fare_estimate_id=estimate_id,
            fare_calculation_id=uuid4(),
        )


def test_pricing_repository_rejects_forged_and_cross_ride_lineage(
    postgres_composition,
) -> None:
    app, request, _, estimate, _ = estimate_and_accept(postgres_composition)
    ride = complete_request_ride(postgres_composition, request)
    service = subject(IdentityType.SERVICE)
    calculation = app.final_calculation(
        service,
        ride_id=ride.ride_id,
        estimate_id=estimate.estimate_id,
        metrics=route(),
        idempotency_key=f"final-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    tampered = calculation.model_copy(
        update={
            "calculation_id": uuid4(),
            "financial_traceability": calculation.financial_traceability.model_copy(
                update={"ride_request_id": uuid4()}
            ),
        }
    )
    with (
        postgres_composition.unit_of_work() as unit,
        pytest.raises(PricingConflict, match="financial_traceability_conflict"),
    ):
        unit.pricing.add_calculation(tampered, correlation_id=uuid4())


def test_pricing_repository_rejects_correction_without_ancestry(
    postgres_composition,
) -> None:
    app, request, _, estimate, _ = estimate_and_accept(postgres_composition)
    ride = complete_request_ride(postgres_composition, request)
    service = subject(IdentityType.SERVICE)
    calculation = app.final_calculation(
        service,
        ride_id=ride.ride_id,
        estimate_id=estimate.estimate_id,
        metrics=route(),
        idempotency_key=f"final-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    corrected = calculation.model_copy(
        update={
            "calculation_id": uuid4(),
            "predecessor_calculation_id": calculation.calculation_id,
            "financial_traceability": calculation.financial_traceability.model_copy(
                update={"fare_calculation_id": uuid4()}
            ),
        }
    )
    with (
        postgres_composition.unit_of_work() as unit,
        pytest.raises(PricingConflict, match="financial_traceability_conflict"),
    ):
        unit.pricing.add_calculation(corrected, correlation_id=uuid4())


def test_policy_estimate_acceptance_and_role_safe_breakdowns(
    postgres_composition,
) -> None:
    app, _, rider, estimate, acceptance = estimate_and_accept(postgres_composition)
    assert acceptance.accepted_amount_minor == estimate.breakdown.rider_total_minor
    assert reconstruct(estimate.calculation_lineage) == estimate.breakdown
    assert estimate.calculation_lineage.audit_event_id == estimate.audit_reference
    assert "ayo_commission_minor" not in app.rider_breakdown(rider, estimate)
    with pytest.raises(PricingConflict, match="pricing_record_not_found"):
        app.rider_breakdown(subject(IdentityType.RIDER), estimate)
    duplicate = app.accept(
        rider,
        estimate.estimate_id,
        idempotency_key=acceptance.idempotency_key,
        at=NOW,
    )
    assert duplicate.acceptance_id == acceptance.acceptance_id
    replay_key = "estimate-changed-replay"
    app.estimate(
        rider,
        ride_request_id=estimate.ride_request_id,
        policy_id=estimate.policy_id,
        metrics=route(distance=5000),
        idempotency_key=replay_key,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    with pytest.raises(PricingConflict, match="idempotency_conflict"):
        app.estimate(
            rider,
            ride_request_id=estimate.ride_request_id,
            policy_id=estimate.policy_id,
            metrics=route(distance=6000),
            idempotency_key=replay_key,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )


def test_expiry_cross_rider_and_unpublished_policy_fail_closed(
    postgres_composition,
) -> None:
    request, rider = ready_request(postgres_composition)
    app = PricingApplication(postgres_composition, estimate_ttl_seconds=1)
    draft = PricingPolicy(
        policy_version=f"draft.{uuid4().hex}",
        service_zone_id=request.service_zone_id,
        service_type="immediate_standard",
        currency="ETB",
        base_fare_minor=1,
        distance_rate_per_km_minor=1,
        time_rate_per_minute_minor=1,
        minimum_fare_minor=1,
        commission_basis_points=0,
        rounding_increment_minor=1,
        effective_from=NOW,
        made_by_identity_id=uuid4(),
        created_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        unit.pricing.add_policy(draft)
    with pytest.raises(PricingConflict, match="access_denied"):
        app.publish_policy(rider, draft.policy_id, at=NOW)
    with pytest.raises(PricingConflict, match="published_policy_required"):
        app.estimate(
            rider,
            ride_request_id=request.request_id,
            policy_id=draft.policy_id,
            metrics=route(),
            idempotency_key=f"estimate-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )
    policy = published_policy(app, request.service_zone_id)
    estimate = app.estimate(
        rider,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    with pytest.raises(PricingConflict, match="estimate_not_found"):
        app.accept(
            subject(IdentityType.RIDER),
            estimate.estimate_id,
            idempotency_key=f"accept-{uuid4()}",
            at=NOW,
        )
    with pytest.raises(PricingConflict, match="estimate_expired"):
        app.accept(
            rider,
            estimate.estimate_id,
            idempotency_key=f"accept-{uuid4()}",
            at=NOW + timedelta(seconds=2),
        )


def test_policy_maker_checker_and_publication_separation(postgres_composition) -> None:
    request, _ = ready_request(postgres_composition)
    app = PricingApplication(postgres_composition)
    maker = subject(IdentityType.STAFF)
    item = PricingPolicy(
        policy_version=f"separation.{uuid4().hex}",
        service_zone_id=request.service_zone_id,
        service_type="immediate_standard",
        currency="ETB",
        base_fare_minor=1,
        distance_rate_per_km_minor=1,
        time_rate_per_minute_minor=1,
        minimum_fare_minor=1,
        commission_basis_points=0,
        rounding_increment_minor=1,
        effective_from=NOW,
        made_by_identity_id=maker.identity_id,
        created_at=NOW,
    )
    app.create_policy(maker, item)
    with pytest.raises(PricingConflict, match="maker_checker_required"):
        app.approve_policy(maker, item.policy_id, at=NOW)
    checker = subject(IdentityType.STAFF)
    app.approve_policy(checker, item.policy_id, at=NOW)
    with pytest.raises(PricingConflict, match="publication_separation_required"):
        app.publish_policy(checker, item.policy_id, at=NOW)


def test_estimate_event_failure_rolls_back_pricing_state(
    postgres_composition, monkeypatch
) -> None:
    request, rider = ready_request(postgres_composition)
    app = PricingApplication(postgres_composition)
    policy = published_policy(app, request.service_zone_id)

    def fail_event(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(PostgresPricingRepository, "_event", fail_event)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        app.estimate(
            rider,
            ride_request_id=request.request_id,
            policy_id=policy.policy_id,
            metrics=route(),
            idempotency_key=f"estimate-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(fare_estimates)
            ).scalar_one()
            == 0
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(pricing_outbox)
            ).scalar_one()
            == 0
        )


def test_final_requires_completed_matching_canonical_ride(postgres_composition) -> None:
    app, request, rider, estimate, _ = estimate_and_accept(postgres_composition)
    service = subject(IdentityType.SERVICE)
    with pytest.raises(PricingConflict, match="completed_canonical_ride_required"):
        app.final_calculation(
            service,
            ride_id=uuid4(),
            estimate_id=estimate.estimate_id,
            metrics=route(),
            idempotency_key=f"final-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )
    # A separately created completed ride cannot be paired with this estimate.
    ride, _, _ = complete_ride(postgres_composition)
    assert ride.ride_request_id != request.request_id
    with pytest.raises(PricingConflict, match="completed_canonical_ride_required"):
        app.final_calculation(
            service,
            ride_id=ride.ride_id,
            estimate_id=estimate.estimate_id,
            metrics=route(),
            idempotency_key=f"final-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )


def test_concurrent_final_calculation_is_single_and_outbox_atomic(
    postgres_composition,
) -> None:
    # Build the estimate from the same canonical request that Dispatch assigns.
    assignment_id, rider, driver = assigned(postgres_composition)
    lifecycle = ActiveRideLifecycleApplication(postgres_composition.unit_of_work)
    ride = lifecycle.start_from_assignment(assignment_id, now=NOW)
    with postgres_composition.unit_of_work() as unit:
        source = unit.pricing.ride_request_source(ride.ride_request_id)
    assert source is not None
    app = PricingApplication(postgres_composition)
    policy = published_policy(app, source["service_zone_id"])
    estimate = app.estimate(
        rider,
        ride_request_id=ride.ride_request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    app.accept(rider, estimate.estimate_id, idempotency_key=f"accept-{uuid4()}", at=NOW)
    service = subject(IdentityType.SERVICE)
    version = 1
    for actor, kind in (
        (driver, LifecycleCommandType.DRIVER_EN_ROUTE),
        (driver, LifecycleCommandType.DRIVER_ARRIVED),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (driver, LifecycleCommandType.RIDE_STARTED),
        (driver, LifecycleCommandType.DESTINATION_ARRIVED),
        (driver, LifecycleCommandType.RIDE_COMPLETED),
    ):
        result = lifecycle.command(
            actor,
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
    key = f"final-{uuid4()}"
    final_metrics = route()

    def calculate_final():
        return app.final_calculation(
            service,
            ride_id=ride.ride_id,
            estimate_id=estimate.estimate_id,
            metrics=final_metrics,
            idempotency_key=key,
            correlation_id=uuid4(),
            at=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, duplicate = list(pool.map(lambda _: calculate_final(), range(2)))
    assert duplicate.calculation_id == first.calculation_id
    breakdown = app.driver_breakdown(driver, first)
    with pytest.raises(PricingConflict, match="pricing_record_not_found"):
        app.driver_breakdown(subject(IdentityType.DRIVER), first)
    assert breakdown["ayo_commission_minor"] > 0
    assert breakdown["projected_net_minor"] < breakdown["gross_minor"]
    assert app.cash_expectation(first)["collection_status"] == "not_recorded"
    assert reconstruct(first.calculation_lineage) == first.breakdown
    assert first.calculation_lineage.audit_event_id == first.audit_reference
    corrected = app.correct_calculation(
        subject(IdentityType.STAFF),
        predecessor_calculation_id=first.calculation_id,
        metrics=route(distance=5100),
        reason_code="pricing.approved_distance_correction",
        idempotency_key=f"correct-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert corrected.predecessor_calculation_id == first.calculation_id
    assert corrected.calculation_id != first.calculation_id
    assert corrected.calculation_lineage.causation_id == first.calculation_id
    assert reconstruct(corrected.calculation_lineage) == corrected.breakdown
    trace = first.financial_traceability
    assert trace.ride_request_id == ride.ride_request_id
    assert trace.dispatch_handoff_id == ride.dispatch_handoff_id
    assert trace.assignment_id == ride.assignment_id
    assert trace.active_ride_id == ride.ride_id
    assert trace.fare_estimate_id == estimate.estimate_id
    assert trace.fare_calculation_id == first.calculation_id
    assert (
        corrected.financial_traceability.predecessor_fare_calculation_id
        == first.calculation_id
    )
    reviewer = subject(IdentityType.STAFF)
    with pytest.raises(PricingConflict, match="financial_journey_not_found"):
        app.financial_journey(reviewer, ride.ride_id, at=NOW)
    grant_trace_read(postgres_composition, reviewer)
    journey = app.financial_journey(reviewer, ride.ride_id, at=NOW)
    assert journey.ride_request_id == ride.ride_request_id
    assert journey.dispatch_handoff_id == ride.dispatch_handoff_id
    assert journey.assignment_id == ride.assignment_id
    assert {item.calculation_id for item in journey.fare_calculations} == {
        first.calculation_id,
        corrected.calculation_id,
    }
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(fare_calculations)
            ).scalar_one()
            == 2
        )
        assert (
            unit.connection.execute(
                select(func.count())
                .select_from(pricing_events)
                .where(pricing_events.c.event_id == first.audit_reference)
            ).scalar_one()
            == 1
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(pricing_events)
            ).scalar_one()
            == 5
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(pricing_outbox)
            ).scalar_one()
            == 5
        )
