from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.dispatch.runtime import (
    CanonicalDispatchApplication,
    DriverOperationalEvidence,
    PickupRouteEvidence,
)
from BACKEND.dispatch.worker_models import (
    EarningCapability,
    WorkerCapabilitySession,
    WorkerSessionConflict,
)
from BACKEND.dispatch.worker_session import WorkerSessionApplication
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict
from BACKEND.persistence.tables import (
    immediate_dispatch_assignments,
    immediate_dispatch_outbox,
)
from BACKEND.session.models import SessionRecord
from tests.integration.test_dispatch_handoff_localization import (
    eligible_driver,
    ready_request,
)

pytestmark = [pytest.mark.integration, pytest.mark.authorization]
# Stay inside the imported synthetic ride request's 15-minute validity window.
NOW = datetime(2026, 7, 16, 0, 5, tzinfo=UTC)


class Supply:
    def __init__(self, item: DriverOperationalEvidence):
        self.item = item

    def shortlist(self, **kwargs):
        assert kwargs["limit"] <= 20
        return (self.item,)


class Routes:
    def __init__(self):
        self.fail_once = False

    def pickup_routes(self, **kwargs):
        if self.fail_once:
            self.fail_once = False
            raise TimeoutError("route_intelligence_timeout")
        item = kwargs["candidates"][0]
        return (
            PickupRouteEvidence(
                driver_id=item.driver_id,
                evidence_id=f"rie-{uuid4()}",
                pickup_eta_seconds=25,
                observed_at=kwargs["at"],
                temporary_restrictions_clear=True,
                traffic_evidence_fresh=True,
                pickup_confidence_bps=9000,
            ),
        )


def setup_runtime(composition):
    request, _ = ready_request(composition)
    candidate = eligible_driver(composition, 25)
    session = SessionRecord(
        subject_id=str(candidate.driver_id),
        identity_id=candidate.driver_id,
        token_hash=uuid4().bytes + uuid4().bytes,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    with composition.unit_of_work() as unit:
        session = unit.sessions.create(session)
        unit.worker_sessions.start(
            WorkerCapabilitySession(
                identity_id=candidate.driver_id,
                identity_session_id=session.session_id,
                capability=EarningCapability.RIDE_DRIVER,
                vehicle_id=candidate.vehicle_id,
                service_zone_id=request.service_zone_id,
                started_at=NOW,
                last_seen_at=NOW,
            )
        )
    operational = DriverOperationalEvidence(
        driver_id=candidate.driver_id,
        vehicle_id=candidate.vehicle_id,
        authorized_vehicle_id=candidate.authorized_vehicle_id,
        account_active=True,
        authenticated_session_active=True,
        eligibility_status="eligible",
        eligibility_expires_at=NOW + timedelta(hours=1),
        vehicle_approved=True,
        supported_services=frozenset({"immediate_standard"}),
        availability="available",
        availability_observed_at=NOW,
        earning_capability="ride_driver",
        fatigue_eligible=True,
        pickup_accessible=True,
        conflicting_commitment=False,
        active_workload_count=0,
        reliability_bps=8000,
        cancellation_history_bps=0,
        opportunity_deficit_bps=2000,
        eligibility_policy_version="driver.eligibility.v1",
    )
    routes = Routes()
    application = CanonicalDispatchApplication(
        composition,
        Supply(operational),
        routes,
        policy_version="dispatch.immediate.v1",
        service_actor_id=uuid4(),
    )
    subject = AuthorizationSubject(
        identity_id=candidate.driver_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
        session_id=session.session_id,
    )
    return request, candidate, routes, application, subject


def test_canonical_start_timeout_retry_and_driver_acceptance(postgres_composition):
    request, _, routes, application, subject = setup_runtime(postgres_composition)
    correlation = uuid4()
    causation = uuid4()
    routes.fail_once = True
    with pytest.raises(TimeoutError):
        application.start(
            ride_request_id=request.request_id,
            idempotency_key="dispatch-start-retry-001",
            correlation_id=correlation,
            causation_id=causation,
            at=NOW,
        )
    handoff, offer = application.start(
        ride_request_id=request.request_id,
        idempotency_key="dispatch-start-retry-001",
        correlation_id=correlation,
        causation_id=causation,
        at=NOW,
    )
    assert offer is not None and handoff.ride_request_id == request.request_id
    assignment = application.respond(
        subject=subject,
        offer_id=offer.offer_id,
        accept=True,
        expected_version=offer.version,
        idempotency_key="canonical-offer-accept-001",
        at=NOW,
    )
    assert assignment is not None
    with postgres_composition.unit_of_work() as unit:
        events = set(
            unit.connection.execute(
                select(immediate_dispatch_outbox.c.event_type)
            ).scalars()
        )
    assert {
        "dispatch.rider.searching",
        "dispatch.rider.driver_found",
        "dispatch.driver.new_offer",
        "dispatch.driver.acceptance_confirmed",
        "dispatch.rider.driver_accepted",
    } <= events


def test_concurrent_duplicate_acceptance_has_one_assignment(postgres_composition):
    request, _, _, application, subject = setup_runtime(postgres_composition)
    _, offer = application.start(
        ride_request_id=request.request_id,
        idempotency_key="dispatch-start-race-001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert offer is not None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result()
            for future in [
                pool.submit(
                    application.respond,
                    subject=subject,
                    offer_id=offer.offer_id,
                    accept=True,
                    expected_version=offer.version,
                    idempotency_key="canonical-offer-race-001",
                    at=NOW,
                ),
                pool.submit(
                    application.respond,
                    subject=subject,
                    offer_id=offer.offer_id,
                    accept=True,
                    expected_version=offer.version,
                    idempotency_key="canonical-offer-race-001",
                    at=NOW,
                ),
            ]
        ]
    assert results[0] == results[1]
    with postgres_composition.unit_of_work() as unit:
        count = unit.connection.execute(
            select(func.count()).select_from(immediate_dispatch_assignments)
        ).scalar_one()
    assert count == 1


def test_one_active_earning_role_is_database_enforced(postgres_composition):
    _, candidate, _, _, subject = setup_runtime(postgres_composition)
    with (
        postgres_composition.unit_of_work() as unit,
        pytest.raises(WorkerSessionConflict, match="go_offline"),
    ):
        unit.worker_sessions.start(
            WorkerCapabilitySession(
                identity_id=candidate.driver_id,
                identity_session_id=subject.session_id,
                capability=EarningCapability.FOOD_COURIER,
                started_at=NOW,
                last_seen_at=NOW,
            )
        )


def test_stopping_ride_driver_mode_revokes_offer_but_not_identity_session(
    postgres_composition,
):
    request, _, _, application, subject = setup_runtime(postgres_composition)
    _, offer = application.start(
        ride_request_id=request.request_id,
        idempotency_key="dispatch-stop-mode-001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert offer is not None
    stopped = WorkerSessionApplication(postgres_composition).stop_ride_driver(
        subject=subject, at=NOW
    )
    assert stopped.state.value == "offline"
    with pytest.raises(HandoffConflict):
        application.respond(
            subject=subject,
            offer_id=offer.offer_id,
            accept=True,
            expected_version=offer.version,
            idempotency_key="dispatch-stop-accept-001",
            at=NOW,
        )
    with postgres_composition.unit_of_work() as unit:
        assert unit.sessions.get(subject.session_id).revoked_at is None
