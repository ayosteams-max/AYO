from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError

from BACKEND.driver_trust.models import (
    DocumentEvidence,
    DriverVehicleAuthorization,
    EligibilityDecision,
    EvidenceStatus,
    OnboardingCase,
    Vehicle,
)
from BACKEND.persistence.tables import (
    driver_document_evidence,
    driver_eligibility_decisions,
    driver_onboarding_cases,
    driver_trust_idempotency,
    driver_vehicle_authorizations,
    driver_vehicles,
)


class ConcurrentDriverTrustChange(RuntimeError):
    pass


class DuplicateEvidence(RuntimeError):
    pass


def _case(row: Any) -> OnboardingCase:
    return OnboardingCase.model_validate(dict(row))


def _evidence(row: Any) -> DocumentEvidence:
    return DocumentEvidence.model_validate(dict(row))


class PostgresDriverTrustRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_case(self, case: OnboardingCase) -> OnboardingCase:
        row = (
            self._connection.execute(
                insert(driver_onboarding_cases)
                .values(**case.model_dump())
                .returning(driver_onboarding_cases)
            )
            .mappings()
            .one()
        )
        return _case(row)

    def get_case(self, case_id: UUID) -> OnboardingCase | None:
        row = (
            self._connection.execute(
                select(driver_onboarding_cases).where(
                    driver_onboarding_cases.c.case_id == case_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _case(row)

    def owner_identity_id(self, *, resource_type: str, resource_id: str) -> UUID | None:
        resource = UUID(resource_id)
        if resource_type == "driver_onboarding_case":
            value = self._connection.execute(
                select(driver_onboarding_cases.c.driver_identity_id).where(
                    driver_onboarding_cases.c.case_id == resource
                )
            ).scalar_one_or_none()
            return cast(UUID | None, value)
        if resource_type == "driver_document_evidence":
            value = self._connection.execute(
                select(driver_document_evidence.c.driver_identity_id).where(
                    driver_document_evidence.c.evidence_id == resource
                )
            ).scalar_one_or_none()
            return cast(UUID | None, value)
        return None

    def save_case(
        self, case: OnboardingCase, *, expected_version: int
    ) -> OnboardingCase:
        row = (
            self._connection.execute(
                update(driver_onboarding_cases)
                .where(
                    driver_onboarding_cases.c.case_id == case.case_id,
                    driver_onboarding_cases.c.version == expected_version,
                )
                .values(
                    state=case.state.value,
                    updated_at=case.updated_at,
                    expires_at=case.expires_at,
                    version=case.version,
                )
                .returning(driver_onboarding_cases)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ConcurrentDriverTrustChange("Onboarding case changed concurrently")
        return _case(row)

    def add_evidence(self, evidence: DocumentEvidence) -> DocumentEvidence:
        values = evidence.model_dump()
        values["reason_codes"] = list(evidence.reason_codes)
        try:
            row = (
                self._connection.execute(
                    insert(driver_document_evidence)
                    .values(**values)
                    .returning(driver_document_evidence)
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            raise DuplicateEvidence(
                "Document evidence was already submitted"
            ) from error
        return _evidence(row)

    def list_current_evidence(
        self, driver_identity_id: UUID
    ) -> Sequence[DocumentEvidence]:
        rows = (
            self._connection.execute(
                select(driver_document_evidence).where(
                    driver_document_evidence.c.driver_identity_id == driver_identity_id,
                    driver_document_evidence.c.superseded_by_evidence_id.is_(None),
                )
            )
            .mappings()
            .all()
        )
        return tuple(_evidence(row) for row in rows)

    def review_evidence(
        self,
        evidence_id: UUID,
        *,
        status: EvidenceStatus,
        reviewer_identity_id: UUID,
        reason_codes: tuple[str, ...],
        reviewed_at: Any,
        expected_version: int,
    ) -> DocumentEvidence:
        if status not in {EvidenceStatus.APPROVED, EvidenceStatus.REJECTED}:
            raise ValueError("Review outcome must be approved or rejected")
        row = (
            self._connection.execute(
                update(driver_document_evidence)
                .where(
                    driver_document_evidence.c.evidence_id == evidence_id,
                    driver_document_evidence.c.version == expected_version,
                    driver_document_evidence.c.status.in_(
                        ["submitted", "under_review"]
                    ),
                )
                .values(
                    status=status.value,
                    reviewer_identity_id=reviewer_identity_id,
                    reason_codes=list(reason_codes),
                    reviewed_at=reviewed_at,
                    version=driver_document_evidence.c.version + 1,
                )
                .returning(driver_document_evidence)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ConcurrentDriverTrustChange("Evidence changed concurrently")
        return _evidence(row)

    def add_vehicle(self, vehicle: Vehicle) -> None:
        values = vehicle.model_dump()
        for name in (
            "accessibility_capabilities",
            "airport_standard_inputs",
            "airport_premium_inputs",
        ):
            values[name] = list(values[name])
        self._connection.execute(insert(driver_vehicles).values(**values))

    def add_vehicle_authorization(
        self, authorization: DriverVehicleAuthorization
    ) -> None:
        values = authorization.model_dump()
        values["reason_codes"] = list(authorization.reason_codes)
        self._connection.execute(insert(driver_vehicle_authorizations).values(**values))

    def append_eligibility(self, decision: EligibilityDecision) -> None:
        values = decision.model_dump()
        values["reason_codes"] = list(decision.reason_codes)
        values["missing_evidence"] = [item.value for item in decision.missing_evidence]
        self._connection.execute(insert(driver_eligibility_decisions).values(**values))

    def reserve_idempotency(
        self,
        *,
        actor_identity_id: UUID,
        key: str,
        operation: str,
        request_hash: str,
        response_reference: UUID,
        created_at: Any,
    ) -> UUID:
        self._connection.execute(
            postgres_insert(driver_trust_idempotency)
            .values(
                actor_identity_id=actor_identity_id,
                idempotency_key=key,
                operation=operation,
                request_hash=request_hash,
                response_reference=response_reference,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                index_elements=["actor_identity_id", "idempotency_key"]
            )
        )
        existing = (
            self._connection.execute(
                select(driver_trust_idempotency)
                .where(
                    driver_trust_idempotency.c.actor_identity_id == actor_identity_id,
                    driver_trust_idempotency.c.idempotency_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            raise RuntimeError("Idempotency reservation was not persisted")
        if (
            existing["operation"] != operation
            or existing["request_hash"] != request_hash
        ):
            raise ValueError("Idempotency key reused with different request")
        return cast(UUID, existing["response_reference"])
