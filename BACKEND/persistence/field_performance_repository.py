import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, false, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.field_operations.models import CaseStatus
from BACKEND.field_performance.engine import FieldPerformanceConflict, readiness
from BACKEND.field_performance.models import (
    PerformanceEvidence,
    PerformanceRecommendation,
    ReadinessAssertion,
    TerritoryPerformanceSummary,
)
from BACKEND.persistence.tables import (
    field_assistance_cases,
    field_partner_assignments,
    field_performance_events,
    field_performance_evidence,
    field_performance_idempotency,
    field_performance_recommendations,
    field_readiness_assertions,
)


def _model(kind, row):
    return kind.model_validate(dict(row))


class PostgresFieldPerformanceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        actor: UUID,
        operation: str,
        key: str,
        payload: str,
        candidate: UUID,
        at: datetime,
    ) -> UUID:
        if not 16 <= len(key) <= 128:
            raise FieldPerformanceConflict("idempotency_key_invalid")
        digest = hashlib.sha256(payload.encode()).hexdigest()
        found = self._connection.execute(
            pg_insert(field_performance_idempotency)
            .values(
                actor_identity_id=actor,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=candidate,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(field_performance_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if found is not None:
            return cast(UUID, found)
        row = (
            self._connection.execute(
                select(field_performance_idempotency).where(
                    field_performance_idempotency.c.actor_identity_id == actor,
                    field_performance_idempotency.c.operation == operation,
                    field_performance_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest:
            raise FieldPerformanceConflict("idempotency_conflict")
        return cast(UUID, row["response_reference"])

    def get_evidence(self, evidence_id: UUID) -> PerformanceEvidence | None:
        row = (
            self._connection.execute(
                select(field_performance_evidence).where(
                    field_performance_evidence.c.evidence_id == evidence_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(PerformanceEvidence, row)

    def append_evidence(self, value: PerformanceEvidence) -> PerformanceEvidence:
        self._connection.execute(
            insert(field_performance_evidence).values(**value.model_dump(mode="json"))
        )
        self._event(
            "evidence",
            value.evidence_id,
            "field.performance.evidence_recorded",
            value.recorded_by_identity_id,
            {"metric": value.metric.value},
            value.recorded_at,
        )
        return value

    def evidence_by_ids(self, ids: tuple[UUID, ...]) -> tuple[PerformanceEvidence, ...]:
        if not ids:
            return ()
        rows = (
            self._connection.execute(
                select(field_performance_evidence).where(
                    field_performance_evidence.c.evidence_id.in_(ids)
                )
            )
            .mappings()
            .all()
        )
        return tuple(_model(PerformanceEvidence, row) for row in rows)

    def partner_evidence(
        self, partner_id: UUID, *, limit: int
    ) -> tuple[PerformanceEvidence, ...]:
        rows = (
            self._connection.execute(
                select(field_performance_evidence)
                .where(field_performance_evidence.c.partner_id == partner_id)
                .order_by(field_performance_evidence.c.recorded_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return tuple(_model(PerformanceEvidence, row) for row in rows)

    def get_readiness_assertion(self, assertion_id: UUID) -> ReadinessAssertion | None:
        row = (
            self._connection.execute(
                select(field_readiness_assertions).where(
                    field_readiness_assertions.c.assertion_id == assertion_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(ReadinessAssertion, row)

    def append_readiness_assertion(
        self, value: ReadinessAssertion
    ) -> ReadinessAssertion:
        self._connection.execute(
            insert(field_readiness_assertions).values(**value.model_dump(mode="json"))
        )
        self._event(
            "readiness",
            value.assertion_id,
            "field.performance.readiness_recorded",
            value.recorded_by_identity_id,
            {"requirement": value.requirement.value, "satisfied": value.satisfied},
            value.recorded_at,
        )
        return value

    def readiness_assertions(
        self, partner_id: UUID, *, limit: int
    ) -> tuple[ReadinessAssertion, ...]:
        rows = (
            self._connection.execute(
                select(field_readiness_assertions)
                .where(field_readiness_assertions.c.partner_id == partner_id)
                .order_by(field_readiness_assertions.c.recorded_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return tuple(_model(ReadinessAssertion, row) for row in rows)

    def get_recommendation(
        self, recommendation_id: UUID
    ) -> PerformanceRecommendation | None:
        row = (
            self._connection.execute(
                select(field_performance_recommendations).where(
                    field_performance_recommendations.c.recommendation_id
                    == recommendation_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(PerformanceRecommendation, row)

    def append_recommendation(
        self, value: PerformanceRecommendation
    ) -> PerformanceRecommendation:
        data = value.model_dump(mode="json")
        data["evidence_ids"] = [str(item) for item in value.evidence_ids]
        data["risks"] = list(value.risks)
        self._connection.execute(
            insert(field_performance_recommendations).values(**data)
        )
        self._event(
            "recommendation",
            value.recommendation_id,
            "field.performance.recommendation_prepared",
            value.recommended_by_identity_id,
            {"kind": value.kind.value, "status": value.status},
            value.created_at,
        )
        return value

    def partner_recommendations(
        self, partner_id: UUID, *, limit: int
    ) -> tuple[PerformanceRecommendation, ...]:
        rows = (
            self._connection.execute(
                select(field_performance_recommendations)
                .where(field_performance_recommendations.c.partner_id == partner_id)
                .order_by(field_performance_recommendations.c.created_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return tuple(_model(PerformanceRecommendation, row) for row in rows)

    def management_summary(
        self, territory_id: UUID | None, *, at: datetime
    ) -> TerritoryPerformanceSummary:
        partner_query = select(field_partner_assignments.c.partner_id).distinct()
        case_query = select(field_assistance_cases.c.status, func.count()).group_by(
            field_assistance_cases.c.status
        )
        if territory_id is not None:
            partner_query = partner_query.where(
                field_partner_assignments.c.territory_id == territory_id
            )
            case_query = case_query.where(
                field_assistance_cases.c.territory_id == territory_id
            )
        partner_ids = tuple(self._connection.execute(partner_query).scalars())
        counts: dict[str, int] = {
            str(row[0]): int(row[1])
            for row in self._connection.execute(case_query).all()
        }
        ready_count = sum(
            readiness(
                partner_id, self.readiness_assertions(partner_id, limit=100), at=at
            ).ready
            for partner_id in partner_ids
        )
        decided = sum(
            counts.get(state.value, 0)
            for state in (
                CaseStatus.APPROVED,
                CaseStatus.RETURNED_FOR_CORRECTION,
                CaseStatus.REJECTED,
            )
        )

        def rate(state: CaseStatus) -> int:
            return 0 if not decided else counts.get(state.value, 0) * 10_000 // decided

        candidate_query = select(
            func.count(func.distinct(field_performance_recommendations.c.partner_id))
        )
        if partner_ids:
            candidate_query = candidate_query.where(
                field_performance_recommendations.c.partner_id.in_(partner_ids)
            )
        elif territory_id is not None:
            candidate_query = candidate_query.where(false())
        candidates = self._connection.execute(candidate_query).scalar_one()
        return TerritoryPerformanceSummary(
            territory_id=territory_id,
            representative_count=len(partner_ids),
            ready_count=ready_count,
            workload_count=sum(counts.values()),
            approval_rate_bps=rate(CaseStatus.APPROVED),
            correction_rate_bps=rate(CaseStatus.RETURNED_FOR_CORRECTION),
            rejection_rate_bps=rate(CaseStatus.REJECTED),
            recommendation_candidates=candidates,
        )

    def _event(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        actor_id: UUID,
        evidence: dict[str, object],
        at: datetime,
    ) -> None:
        self._connection.execute(
            insert(field_performance_events).values(
                event_id=uuid4(),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                actor_identity_id=actor_id,
                evidence=evidence,
                occurred_at=at,
            )
        )
