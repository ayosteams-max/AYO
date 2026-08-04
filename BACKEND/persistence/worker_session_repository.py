from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.dispatch.worker_models import (
    EarningCapability,
    WorkerCapabilitySession,
    WorkerSessionConflict,
)
from BACKEND.persistence.tables import sessions, worker_capability_sessions


class PostgresWorkerSessionRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_active(
        self, identity_id: UUID, *, lock: bool = False
    ) -> WorkerCapabilitySession | None:
        statement = select(worker_capability_sessions).where(
            worker_capability_sessions.c.identity_id == identity_id,
            worker_capability_sessions.c.state == "online",
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return (
            None if row is None else WorkerCapabilitySession.model_validate(dict(row))
        )

    def start(self, item: WorkerCapabilitySession) -> WorkerCapabilitySession:
        authenticated = self._connection.execute(
            select(sessions.c.session_id).where(
                sessions.c.session_id == item.identity_session_id,
                sessions.c.identity_id == item.identity_id,
                sessions.c.revoked_at.is_(None),
                sessions.c.expires_at > item.started_at,
            )
        ).scalar_one_or_none()
        if authenticated is None:
            raise WorkerSessionConflict("authenticated_session_required")
        current = self.get_active(item.identity_id, lock=True)
        if current is not None:
            if (
                current.capability is item.capability
                and current.vehicle_id == item.vehicle_id
                and current.service_zone_id == item.service_zone_id
            ):
                return current
            raise WorkerSessionConflict("worker_must_go_offline_before_switching")
        try:
            self._connection.execute(
                insert(worker_capability_sessions).values(**item.model_dump())
            )
        except IntegrityError as error:
            raise WorkerSessionConflict(
                "worker_must_go_offline_before_switching"
            ) from error
        return item

    def stop(
        self,
        *,
        identity_id: UUID,
        capability: EarningCapability,
        at: datetime,
    ) -> WorkerCapabilitySession:
        current = self.get_active(identity_id, lock=True)
        if current is None or current.capability is not capability:
            raise WorkerSessionConflict("ride_driver_mode_not_online")
        row = (
            self._connection.execute(
                update(worker_capability_sessions)
                .where(
                    worker_capability_sessions.c.worker_session_id
                    == current.worker_session_id,
                    worker_capability_sessions.c.version == current.version,
                    worker_capability_sessions.c.state == "online",
                )
                .values(
                    state="offline",
                    stopped_at=at,
                    last_seen_at=at,
                    version=current.version + 1,
                )
                .returning(worker_capability_sessions)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise WorkerSessionConflict("worker_session_changed")
        return WorkerCapabilitySession.model_validate(dict(row))

    def ride_driver_online(
        self,
        *,
        identity_id: UUID,
        vehicle_id: UUID,
        service_zone_id: UUID,
        now: datetime,
        lock: bool = False,
    ) -> bool:
        statement = (
            select(worker_capability_sessions.c.worker_session_id)
            .join(
                sessions,
                sessions.c.session_id
                == worker_capability_sessions.c.identity_session_id,
            )
            .where(
                worker_capability_sessions.c.identity_id == identity_id,
                worker_capability_sessions.c.capability == "ride_driver",
                worker_capability_sessions.c.vehicle_id == vehicle_id,
                worker_capability_sessions.c.service_zone_id == service_zone_id,
                worker_capability_sessions.c.state == "online",
                worker_capability_sessions.c.started_at <= now,
                sessions.c.identity_id == identity_id,
                sessions.c.revoked_at.is_(None),
                sessions.c.expires_at > now,
            )
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self._connection.execute(statement).scalar_one_or_none() is not None
