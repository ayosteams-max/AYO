from datetime import datetime
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.dispatch.worker_models import (
    EarningCapability,
    WorkerCapabilitySession,
    WorkerSessionConflict,
)
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition


class WorkerSessionApplication:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    @staticmethod
    def _driver(subject: AuthorizationSubject) -> tuple[UUID, UUID]:
        if (
            subject.identity_type is not IdentityType.DRIVER
            or subject.session_id is None
        ):
            raise WorkerSessionConflict("driver_authentication_required")
        return subject.identity_id, subject.session_id

    def start_ride_driver(
        self,
        *,
        subject: AuthorizationSubject,
        vehicle_id: UUID,
        service_zone_id: UUID,
        at: datetime,
    ) -> WorkerCapabilitySession:
        identity_id, session_id = self._driver(subject)
        item = WorkerCapabilitySession(
            identity_id=identity_id,
            identity_session_id=session_id,
            capability=EarningCapability.RIDE_DRIVER,
            vehicle_id=vehicle_id,
            service_zone_id=service_zone_id,
            started_at=at,
            last_seen_at=at,
        )
        with self._composition.unit_of_work() as unit:
            if not unit.handoff_dispatch.eligibility_current(
                identity_id, vehicle_id, now=at
            ):
                raise WorkerSessionConflict("driver_not_eligible")
            return unit.worker_sessions.start(item)

    def stop_ride_driver(
        self, *, subject: AuthorizationSubject, at: datetime
    ) -> WorkerCapabilitySession:
        identity_id, _ = self._driver(subject)
        with self._composition.unit_of_work() as unit:
            stopped = unit.worker_sessions.stop(
                identity_id=identity_id,
                capability=EarningCapability.RIDE_DRIVER,
                at=at,
            )
            unit.handoff_dispatch.revoke_driver_offer(identity_id, at=at)
            return stopped

    def current(
        self, *, subject: AuthorizationSubject
    ) -> WorkerCapabilitySession | None:
        identity_id, _ = self._driver(subject)
        with self._composition.unit_of_work() as unit:
            return unit.worker_sessions.get_active(identity_id)
