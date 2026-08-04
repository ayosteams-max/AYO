import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.persistence.errors import OptimisticConcurrencyError, PersistenceError
from BACKEND.persistence.tables import (
    mobility_availability_evaluations,
    mobility_product_availability,
    mobility_service_area_geometries,
    mobility_service_areas,
)
from BACKEND.service_area.models import (
    AvailabilityEvaluation,
    AvailabilityOutcome,
    ProductAvailability,
    RideProductCode,
    ServiceArea,
    ServiceAreaGeometry,
    ServiceAreaState,
)


class ServiceAreaConflict(PersistenceError):
    pass


class InvalidBoundaryError(ValueError):
    pass


class PostgresServiceAreaRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, area: ServiceArea) -> ServiceArea:
        try:
            self._connection.execute(
                insert(mobility_service_areas).values(**area.model_dump(mode="python"))
            )
        except IntegrityError as error:
            raise ServiceAreaConflict(
                "Service Area identity or name already exists"
            ) from error
        return area

    def get(self, service_area_id: UUID) -> ServiceArea | None:
        row = (
            self._connection.execute(
                select(mobility_service_areas).where(
                    mobility_service_areas.c.service_area_id == service_area_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ServiceArea.model_validate(dict(row))

    def save(self, area: ServiceArea, *, expected_version: int) -> ServiceArea:
        row = (
            self._connection.execute(
                update(mobility_service_areas)
                .where(
                    mobility_service_areas.c.service_area_id == area.service_area_id,
                    mobility_service_areas.c.version == expected_version,
                )
                .values(
                    state=area.state.value,
                    effective_from=area.effective_from,
                    effective_until=area.effective_until,
                    updated_at=area.updated_at,
                    version=area.version,
                )
                .returning(mobility_service_areas)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Service Area changed concurrently")
        return ServiceArea.model_validate(dict(row))

    def add_geometry(
        self,
        *,
        geometry_id: UUID,
        service_area_id: UUID,
        geometry_version: int,
        boundary_wkt: str,
        srid: int,
        provenance: str,
        recorded_at: datetime,
    ) -> ServiceAreaGeometry:
        if srid != 4326:
            raise InvalidBoundaryError("Service Area geometry must use SRID 4326")
        candidate = func.ST_Multi(func.ST_GeomFromText(boundary_wkt, srid))
        result = self._connection.execute(
            select(
                func.ST_IsValid(candidate),
                func.GeometryType(candidate),
                func.ST_AsEWKB(func.ST_Normalize(candidate)),
            )
        ).one()
        if not result[0] or result[1] != "MULTIPOLYGON":
            raise InvalidBoundaryError(
                "Boundary must be a valid Polygon or MultiPolygon"
            )
        content_hash = hashlib.sha256(bytes(result[2])).hexdigest()
        record = ServiceAreaGeometry(
            geometry_id=geometry_id,
            service_area_id=service_area_id,
            geometry_version=geometry_version,
            provenance=provenance,
            content_hash=content_hash,
            recorded_at=recorded_at,
        )
        try:
            self._connection.execute(
                insert(mobility_service_area_geometries).values(
                    **record.model_dump(mode="python"),
                    boundary=candidate,
                )
            )
        except IntegrityError as error:
            raise ServiceAreaConflict(
                "Geometry version or content already exists"
            ) from error
        return record

    def current_geometry(self, service_area_id: UUID) -> ServiceAreaGeometry | None:
        row = (
            self._connection.execute(
                select(
                    mobility_service_area_geometries.c.geometry_id,
                    mobility_service_area_geometries.c.service_area_id,
                    mobility_service_area_geometries.c.geometry_version,
                    mobility_service_area_geometries.c.provenance,
                    mobility_service_area_geometries.c.content_hash,
                    mobility_service_area_geometries.c.recorded_at,
                )
                .where(
                    mobility_service_area_geometries.c.service_area_id
                    == service_area_id
                )
                .order_by(mobility_service_area_geometries.c.geometry_version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ServiceAreaGeometry.model_validate(dict(row))

    def put_availability(
        self, availability: ProductAvailability, *, expected_version: int | None
    ) -> ProductAvailability:
        if expected_version is None:
            try:
                self._connection.execute(
                    insert(mobility_product_availability).values(
                        **availability.model_dump(mode="python")
                    )
                )
            except IntegrityError as error:
                raise ServiceAreaConflict(
                    "Product availability already exists"
                ) from error
            return availability
        row = (
            self._connection.execute(
                update(mobility_product_availability)
                .where(
                    mobility_product_availability.c.service_area_id
                    == availability.service_area_id,
                    mobility_product_availability.c.product_code
                    == availability.product_code.value,
                    mobility_product_availability.c.version == expected_version,
                )
                .values(
                    state=availability.state.value,
                    effective_from=availability.effective_from,
                    effective_until=availability.effective_until,
                    reason_classification=availability.reason_classification,
                    provenance=availability.provenance,
                    updated_at=availability.updated_at,
                    version=availability.version,
                )
                .returning(mobility_product_availability)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError(
                "Product availability changed concurrently"
            )
        return ProductAvailability.model_validate(dict(row))

    def get_availability(
        self, service_area_id: UUID, product_code: RideProductCode
    ) -> ProductAvailability | None:
        row = (
            self._connection.execute(
                select(mobility_product_availability).where(
                    mobility_product_availability.c.service_area_id == service_area_id,
                    mobility_product_availability.c.product_code == product_code.value,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ProductAvailability.model_validate(dict(row))

    def evaluate(
        self,
        *,
        longitude: float,
        latitude: float,
        product_code: RideProductCode,
        intended_at: datetime,
    ) -> dict[str, object]:
        point = func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326)
        latest = (
            select(
                mobility_service_area_geometries.c.service_area_id,
                func.max(mobility_service_area_geometries.c.geometry_version).label(
                    "geometry_version"
                ),
            )
            .group_by(mobility_service_area_geometries.c.service_area_id)
            .subquery()
        )
        rows = (
            self._connection.execute(
                select(
                    mobility_service_areas,
                    mobility_service_area_geometries.c.geometry_id,
                    mobility_service_area_geometries.c.geometry_version,
                    mobility_product_availability,
                )
                .join(
                    latest,
                    latest.c.service_area_id
                    == mobility_service_areas.c.service_area_id,
                )
                .join(
                    mobility_service_area_geometries,
                    and_(
                        mobility_service_area_geometries.c.service_area_id
                        == latest.c.service_area_id,
                        mobility_service_area_geometries.c.geometry_version
                        == latest.c.geometry_version,
                    ),
                )
                .outerjoin(
                    mobility_product_availability,
                    and_(
                        mobility_product_availability.c.service_area_id
                        == mobility_service_areas.c.service_area_id,
                        mobility_product_availability.c.product_code
                        == product_code.value,
                    ),
                )
                .where(
                    func.ST_Covers(mobility_service_area_geometries.c.boundary, point)
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            return {
                "outcome": AvailabilityOutcome.OUTSIDE_SERVICE_AREA
                if not rows
                else AvailabilityOutcome.UNKNOWN_OR_UNVERIFIABLE
            }
        row = rows[0]
        state = ServiceAreaState(row["state"])
        if state is ServiceAreaState.TEMPORARILY_SUSPENDED:
            outcome = AvailabilityOutcome.TEMPORARILY_UNAVAILABLE
        elif (
            state is not ServiceAreaState.ACTIVE
            or (row["effective_from"] and intended_at < row["effective_from"])
            or (row["effective_until"] and intended_at >= row["effective_until"])
        ):
            outcome = AvailabilityOutcome.SERVICE_AREA_INACTIVE
        elif row["availability_id"] is None:
            outcome = AvailabilityOutcome.PRODUCT_UNAVAILABLE
        elif intended_at < row["effective_from_1"] or (
            row["effective_until_1"] and intended_at >= row["effective_until_1"]
        ):
            outcome = AvailabilityOutcome.NOT_YET_LAUNCHED
        else:
            outcome = {
                "available": AvailabilityOutcome.AVAILABLE,
                "temporarily_unavailable": AvailabilityOutcome.TEMPORARILY_UNAVAILABLE,
                "not_yet_launched": AvailabilityOutcome.NOT_YET_LAUNCHED,
                "retired": AvailabilityOutcome.PRODUCT_UNAVAILABLE,
            }[row["state_1"]]
        return {
            "outcome": outcome,
            "service_area_id": row["service_area_id"],
            "service_area_version": row["version"],
            "geometry_id": row["geometry_id"],
            "geometry_version": row["geometry_version"],
            "availability_id": row["availability_id"],
            "availability_version": row["version_1"],
        }

    def append_evaluation(
        self, evaluation: AvailabilityEvaluation
    ) -> AvailabilityEvaluation:
        self._connection.execute(
            insert(mobility_availability_evaluations).values(
                **evaluation.model_dump(mode="python")
            )
        )
        return evaluation
