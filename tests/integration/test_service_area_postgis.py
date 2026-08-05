from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select, text

from BACKEND.persistence.service_area_repository import (
    InvalidBoundaryError,
    PostgresServiceAreaRepository,
)
from BACKEND.persistence.tables import (
    account_role_assignments,
    audit_events,
    canonical_subjects,
    identity_accounts,
    mobility_availability_evaluations,
    mobility_service_area_geometries,
    permissions,
    persistence_domain_events,
    persistence_outbox,
    role_permissions,
    roles,
)
from BACKEND.persistence.trace import TraceContext
from BACKEND.service_area.application import (
    ConfigureProductAvailability,
    CreateServiceArea,
    RecordBoundary,
    ServiceAreaApplicationService,
)
from BACKEND.service_area.models import (
    AvailabilityEvaluation,
    AvailabilityOutcome,
    ProductAvailability,
    ProductAvailabilityState,
    RideProductCode,
    ServiceArea,
    ServiceAreaState,
)

pytestmark = [pytest.mark.integration, pytest.mark.service_area]
NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def _admin(engine) -> UUID:
    account_id, subject_id, role_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(canonical_subjects).values(
                subject_id=subject_id,
                subject_kind="human",
                created_at=NOW,
                version=1,
            )
        )
        connection.execute(
            insert(identity_accounts).values(
                account_id=account_id,
                subject_id=subject_id,
                state="active",
                created_at=NOW,
                updated_at=NOW,
                version=1,
                failed_attempt_count=0,
                credential_change_required=False,
            )
        )
        connection.execute(
            insert(roles).values(
                role_id=role_id,
                code=f"service_area_admin_{account_id}",
                description="service area test administrator",
                system_managed=False,
                created_at=NOW,
                version=1,
            )
        )
        for code in (
            "mobility.service_area.create",
            "mobility.service_area.manage",
            "mobility.service_area.evaluate",
        ):
            permission_id = uuid4()
            connection.execute(
                insert(permissions).values(
                    permission_id=permission_id,
                    code=code,
                    description=code,
                    created_at=NOW,
                )
            )
            connection.execute(
                insert(role_permissions).values(
                    role_id=role_id,
                    permission_id=permission_id,
                    granted_at=NOW,
                )
            )
        connection.execute(
            insert(account_role_assignments).values(
                assignment_id=uuid4(),
                account_id=account_id,
                role_id=role_id,
                assigned_by_account_id=account_id,
                assigned_at=NOW,
                version=1,
            )
        )
    return account_id


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def _area() -> ServiceArea:
    return ServiceArea(
        service_area_id=uuid4(),
        internal_name=f"test-{uuid4()}",
        created_at=NOW,
        updated_at=NOW,
    )


def test_postgis_extension_geometry_index_and_boundary_semantics(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        repository = PostgresServiceAreaRepository(connection)
        area = repository.create(_area())
        geometry = repository.add_geometry(
            geometry_id=uuid4(),
            service_area_id=area.service_area_id,
            geometry_version=1,
            boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
            srid=4326,
            provenance="certification-fixture",
            recorded_at=NOW,
        )
        boundary_covered = connection.execute(
            select(
                func.ST_Covers(
                    mobility_service_area_geometries.c.boundary,
                    func.ST_SetSRID(func.ST_Point(38, 8.5), 4326),
                )
            ).where(
                mobility_service_area_geometries.c.geometry_id == geometry.geometry_id
            )
        ).scalar_one()
        indexes = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='ayo' AND tablename="
                "'mobility_service_area_geometries'"
            )
        ).scalars()

    assert boundary_covered is True
    assert any("USING gist" in definition for definition in indexes)


def test_polygon_and_multipolygon_are_normalized_and_invalid_inputs_rejected(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        repository = PostgresServiceAreaRepository(connection)
        first = repository.create(_area())
        second = repository.create(_area())
        polygon = repository.add_geometry(
            geometry_id=uuid4(),
            service_area_id=first.service_area_id,
            geometry_version=1,
            boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
            srid=4326,
            provenance="polygon",
            recorded_at=NOW,
        )
        multipolygon = repository.add_geometry(
            geometry_id=uuid4(),
            service_area_id=second.service_area_id,
            geometry_version=1,
            boundary_wkt="MULTIPOLYGON(((40 8,41 8,41 9,40 9,40 8)))",
            srid=4326,
            provenance="multipolygon",
            recorded_at=NOW,
        )
        with pytest.raises(InvalidBoundaryError):
            repository.add_geometry(
                geometry_id=uuid4(),
                service_area_id=first.service_area_id,
                geometry_version=2,
                boundary_wkt="POLYGON((0 0,1 1,1 0,0 1,0 0))",
                srid=4326,
                provenance="invalid",
                recorded_at=NOW,
            )
        with pytest.raises(InvalidBoundaryError, match="SRID 4326"):
            repository.add_geometry(
                geometry_id=uuid4(),
                service_area_id=first.service_area_id,
                geometry_version=2,
                boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
                srid=3857,
                provenance="wrong-srid",
                recorded_at=NOW,
            )

    assert polygon.content_hash != multipolygon.content_hash


def test_evaluation_is_append_only_and_contains_versioned_provenance(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        repository = PostgresServiceAreaRepository(connection)
        area = repository.create(_area())
        geometry = repository.add_geometry(
            geometry_id=uuid4(),
            service_area_id=area.service_area_id,
            geometry_version=1,
            boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
            srid=4326,
            provenance="evaluation",
            recorded_at=NOW,
        )
        availability = repository.put_availability(
            ProductAvailability(
                availability_id=uuid4(),
                service_area_id=area.service_area_id,
                product_code=RideProductCode.STANDARD,
                state=ProductAvailabilityState.AVAILABLE,
                effective_from=NOW,
                reason_classification="launch_authorized",
                provenance="test",
                created_at=NOW,
                updated_at=NOW,
            ),
            expected_version=None,
        )
        evaluation = repository.append_evaluation(
            AvailabilityEvaluation(
                evaluation_id=uuid4(),
                pickup_reference="pickup:test",
                product_code=RideProductCode.STANDARD,
                intended_service_at=NOW,
                evaluated_at=NOW,
                service_area_id=area.service_area_id,
                service_area_version=area.version,
                geometry_id=geometry.geometry_id,
                geometry_version=geometry.geometry_version,
                availability_id=availability.availability_id,
                availability_version=availability.version,
                outcome=AvailabilityOutcome.AVAILABLE,
                correlation_id=uuid4(),
                request_id=uuid4(),
            )
        )
        stored = (
            connection.execute(
                select(mobility_availability_evaluations).where(
                    mobility_availability_evaluations.c.evaluation_id
                    == evaluation.evaluation_id
                )
            )
            .mappings()
            .one()
        )

    assert stored["geometry_version"] == 1
    assert stored["availability_version"] == 1
    assert stored["service_area_version"] == 1


def test_pickup_drives_available_outside_and_product_outcomes(postgres_engine) -> None:
    with postgres_engine.begin() as connection:
        repository = PostgresServiceAreaRepository(connection)
        area = repository.create(
            _area().model_copy(
                update={
                    "state": ServiceAreaState.ACTIVE,
                    "effective_from": NOW,
                }
            )
        )
        repository.add_geometry(
            geometry_id=uuid4(),
            service_area_id=area.service_area_id,
            geometry_version=1,
            boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
            srid=4326,
            provenance="evaluation",
            recorded_at=NOW,
        )
        repository.put_availability(
            ProductAvailability(
                availability_id=uuid4(),
                service_area_id=area.service_area_id,
                product_code=RideProductCode.STANDARD,
                state=ProductAvailabilityState.AVAILABLE,
                effective_from=NOW,
                reason_classification="launch_authorized",
                provenance="test",
                created_at=NOW,
                updated_at=NOW,
            ),
            expected_version=None,
        )
        available = repository.evaluate(
            longitude=38.5,
            latitude=8.5,
            product_code=RideProductCode.STANDARD,
            intended_at=NOW,
        )
        product_unavailable = repository.evaluate(
            longitude=38.5,
            latitude=8.5,
            product_code=RideProductCode.PREMIUM,
            intended_at=NOW,
        )
        outside = repository.evaluate(
            longitude=40,
            latitude=10,
            product_code=RideProductCode.STANDARD,
            intended_at=NOW,
        )

    assert available["outcome"] is AvailabilityOutcome.AVAILABLE
    assert product_unavailable["outcome"] is AvailabilityOutcome.PRODUCT_UNAVAILABLE
    assert outside["outcome"] is AvailabilityOutcome.OUTSIDE_SERVICE_AREA


def test_application_idempotency_concurrency_audit_outbox_and_restart(
    postgres_engine,
) -> None:
    actor = _admin(postgres_engine)
    service = ServiceAreaApplicationService(postgres_engine)
    command = CreateServiceArea(internal_name=f"internal-{uuid4()}")
    created = service.create(
        actor_account_id=actor,
        command=command,
        idempotency_key="service-area-create-0001",
        trace=_trace(),
        at=NOW,
    )
    replay = service.create(
        actor_account_id=actor,
        command=command,
        idempotency_key="service-area-create-0001",
        trace=_trace(),
        at=NOW,
    )
    assert replay.service_area_id == created.service_area_id
    approved = service.transition(
        actor_account_id=actor,
        service_area_id=created.service_area_id,
        target=ServiceAreaState.APPROVED,
        expected_version=1,
        idempotency_key="service-area-approve-0001",
        trace=_trace(),
        at=NOW,
    )
    with pytest.raises(ValueError, match="Stale"):
        service.transition(
            actor_account_id=actor,
            service_area_id=created.service_area_id,
            target=ServiceAreaState.RETIRED,
            expected_version=1,
            idempotency_key="service-area-stale-0001",
            trace=_trace(),
            at=NOW,
        )
    service.record_boundary(
        actor_account_id=actor,
        service_area_id=created.service_area_id,
        geometry_version=1,
        command=RecordBoundary(
            boundary_wkt="POLYGON((38 8,39 8,39 9,38 9,38 8))",
            provenance="application-test",
        ),
        idempotency_key="service-area-geometry-0001",
        trace=_trace(),
        at=NOW,
    )
    service.configure_product(
        actor_account_id=actor,
        service_area_id=created.service_area_id,
        command=ConfigureProductAvailability(
            product_code=RideProductCode.STANDARD,
            state=ProductAvailabilityState.AVAILABLE,
            effective_from=NOW,
            reason_classification="launch_authorized",
            provenance="application-test",
        ),
        expected_version=None,
        idempotency_key="service-area-product-0001",
        trace=_trace(),
        at=NOW,
    )
    active = service.transition(
        actor_account_id=actor,
        service_area_id=created.service_area_id,
        target=ServiceAreaState.ACTIVE,
        expected_version=approved.version,
        idempotency_key="service-area-activate-0001",
        trace=_trace(),
        at=NOW,
    )
    restarted = ServiceAreaApplicationService(postgres_engine)
    with restarted._uow() as unit:
        persisted = unit.service_areas.get(active.service_area_id)
    with postgres_engine.connect() as connection:
        events = connection.execute(
            select(func.count())
            .select_from(persistence_domain_events)
            .where(
                persistence_domain_events.c.aggregate_id == str(active.service_area_id)
            )
        ).scalar_one()
        outbox = connection.execute(
            select(func.count())
            .select_from(persistence_outbox)
            .join(
                persistence_domain_events,
                persistence_domain_events.c.event_id == persistence_outbox.c.event_id,
            )
            .where(
                persistence_domain_events.c.aggregate_id == str(active.service_area_id)
            )
        ).scalar_one()
        audits = connection.execute(
            select(func.count())
            .select_from(audit_events)
            .where(audit_events.c.resource_id == str(active.service_area_id))
        ).scalar_one()

    assert persisted == active
    assert events == outbox == audits == 5
