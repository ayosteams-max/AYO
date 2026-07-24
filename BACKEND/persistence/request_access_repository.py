from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from BACKEND.persistence.errors import OptimisticConcurrencyError, PersistenceError
from BACKEND.persistence.tables import (
    request_access_channel_capabilities,
    request_access_continuity_references,
    request_access_interaction_provenance,
    request_access_source_adapters,
)
from BACKEND.request_access.models import (
    ChannelActionCapability,
    ContinuityReference,
    InteractionProvenanceRecord,
    SourceAdapter,
)


class RequestAccessConflict(PersistenceError):
    pass


def _record_from_row(
    row: Mapping[str, Any] | RowMapping,
) -> InteractionProvenanceRecord:
    values = dict(row)
    values["continuity_reference"] = None
    return InteractionProvenanceRecord.model_validate(values)


class PostgresRequestAccessRepository:
    """Transaction-scoped storage with append-only provenance boundaries."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def register_adapter(self, adapter: SourceAdapter) -> SourceAdapter:
        try:
            self._connection.execute(
                insert(request_access_source_adapters).values(
                    **adapter.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise RequestAccessConflict(
                "Source adapter identity or version already exists"
            ) from error
        return adapter

    def get_adapter(self, adapter_id: UUID) -> SourceAdapter | None:
        row = (
            self._connection.execute(
                select(request_access_source_adapters).where(
                    request_access_source_adapters.c.adapter_id == adapter_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else SourceAdapter.model_validate(dict(row))

    def put_capability(
        self,
        capability: ChannelActionCapability,
        *,
        expected_version: int | None,
    ) -> ChannelActionCapability:
        if expected_version is None:
            try:
                self._connection.execute(
                    insert(request_access_channel_capabilities).values(
                        **capability.model_dump(mode="python")
                    )
                )
            except IntegrityError as error:
                raise RequestAccessConflict(
                    "Channel action capability already exists"
                ) from error
            return capability
        row = (
            self._connection.execute(
                update(request_access_channel_capabilities)
                .where(
                    request_access_channel_capabilities.c.capability_id
                    == capability.capability_id,
                    request_access_channel_capabilities.c.version == expected_version,
                )
                .values(
                    state=capability.state.value,
                    effective_from=capability.effective_from,
                    effective_until=capability.effective_until,
                    version=capability.version,
                    updated_at=capability.updated_at,
                )
                .returning(request_access_channel_capabilities)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError(
                "Channel action capability changed concurrently"
            )
        return ChannelActionCapability.model_validate(dict(row))

    def get_capability(
        self,
        *,
        target_domain: str,
        command_type: str,
        adapter_id: UUID,
    ) -> ChannelActionCapability | None:
        row = (
            self._connection.execute(
                select(request_access_channel_capabilities).where(
                    request_access_channel_capabilities.c.target_domain
                    == target_domain,
                    request_access_channel_capabilities.c.command_type == command_type,
                    request_access_channel_capabilities.c.adapter_id == adapter_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        return (
            None if row is None else ChannelActionCapability.model_validate(dict(row))
        )

    def append_continuity(self, reference: ContinuityReference) -> ContinuityReference:
        try:
            self._connection.execute(
                insert(request_access_continuity_references).values(
                    **reference.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise RequestAccessConflict(
                "Continuity reference already exists"
            ) from error
        return reference

    def get_continuity_by_hash(self, reference_hash: str) -> ContinuityReference | None:
        row = (
            self._connection.execute(
                select(request_access_continuity_references).where(
                    request_access_continuity_references.c.reference_hash
                    == reference_hash
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ContinuityReference.model_validate(dict(row))

    def append_provenance(
        self, record: InteractionProvenanceRecord
    ) -> InteractionProvenanceRecord:
        values = record.model_dump(mode="python")
        values["continuity_id"] = record.continuity_id
        values["interface_accommodation_references"] = list(
            record.interface_accommodation_references
        )
        try:
            self._connection.execute(
                insert(request_access_interaction_provenance).values(**values)
            )
        except IntegrityError as error:
            raise RequestAccessConflict(
                "Interaction provenance identity, initiation, or idempotency conflicts"
            ) from error
        return record

    def get_provenance(self, provenance_id: UUID) -> InteractionProvenanceRecord | None:
        row = (
            self._connection.execute(
                select(request_access_interaction_provenance).where(
                    request_access_interaction_provenance.c.provenance_id
                    == provenance_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _record_from_row(row)

    def find_by_target(
        self,
        *,
        target_domain: str,
        target_type: str,
        target_id: str,
        limit: int = 100,
    ) -> list[InteractionProvenanceRecord]:
        if not 1 <= limit <= 500:
            raise ValueError("Provenance query limit must be between 1 and 500")
        rows = (
            self._connection.execute(
                select(request_access_interaction_provenance)
                .where(
                    request_access_interaction_provenance.c.target_domain
                    == target_domain,
                    request_access_interaction_provenance.c.target_type == target_type,
                    request_access_interaction_provenance.c.target_id == target_id,
                )
                .order_by(
                    request_access_interaction_provenance.c.accepted_at,
                    request_access_interaction_provenance.c.provenance_id,
                )
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [_record_from_row(row) for row in rows]
