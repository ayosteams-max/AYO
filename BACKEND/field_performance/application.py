from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.field_performance.engine import (
    FieldPerformanceConflict,
    readiness,
    validate_recommendation,
)
from BACKEND.field_performance.models import (
    EvidenceUnit,
    PerformanceEvidence,
    PerformanceMetric,
    PerformanceRecommendation,
    ReadinessAssertion,
    ReadinessRequirement,
    RecommendationKind,
    RepresentativePerformanceView,
    TerritoryPerformanceSummary,
)


class FieldPerformanceApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def record_evidence(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        territory_id: UUID | None,
        metric: PerformanceMetric,
        value: int,
        unit: EvidenceUnit,
        source_domain: str,
        source_event_id: UUID,
        evidence_reference: str,
        window_starts_at: datetime,
        window_ends_at: datetime,
        policy_version: str,
        supersedes_evidence_id: UUID | None,
        idempotency_key: str,
        at: datetime,
    ) -> PerformanceEvidence:
        with self._composition.unit_of_work() as unit_of_work:
            self._permission(
                unit_of_work, subject, "field_performance.evidence.record", at
            )
            evidence_id = unit_of_work.field_performance.reserve(
                subject.identity_id,
                "evidence.record",
                idempotency_key,
                f"{partner_id}:{territory_id}:{metric}:{value}:{unit}:{source_domain}:{source_event_id}:{evidence_reference}:{window_starts_at}:{window_ends_at}:{policy_version}:{supersedes_evidence_id}",
                uuid4(),
                at,
            )
            existing = unit_of_work.field_performance.get_evidence(evidence_id)
            if existing is not None:
                return existing
            if unit_of_work.field_operations.get_partner(partner_id) is None:
                raise FieldPerformanceConflict("performance_partner_not_found")
            return unit_of_work.field_performance.append_evidence(
                PerformanceEvidence(
                    evidence_id=evidence_id,
                    partner_id=partner_id,
                    territory_id=territory_id,
                    metric=metric,
                    value=value,
                    unit=unit,
                    source_domain=source_domain,
                    source_event_id=source_event_id,
                    evidence_reference=evidence_reference,
                    window_starts_at=window_starts_at,
                    window_ends_at=window_ends_at,
                    policy_version=policy_version,
                    recorded_by_identity_id=subject.identity_id,
                    supersedes_evidence_id=supersedes_evidence_id,
                    recorded_at=at,
                )
            )

    def record_readiness(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        requirement: ReadinessRequirement,
        satisfied: bool,
        source_domain: str,
        source_event_id: UUID,
        evidence_reference: str,
        effective_at: datetime,
        expires_at: datetime | None,
        idempotency_key: str,
        at: datetime,
    ) -> ReadinessAssertion:
        with self._composition.unit_of_work() as unit_of_work:
            self._permission(
                unit_of_work, subject, "field_performance.readiness.record", at
            )
            assertion_id = unit_of_work.field_performance.reserve(
                subject.identity_id,
                "readiness.record",
                idempotency_key,
                f"{partner_id}:{requirement}:{satisfied}:{source_domain}:{source_event_id}:{evidence_reference}:{effective_at}:{expires_at}",
                uuid4(),
                at,
            )
            existing = unit_of_work.field_performance.get_readiness_assertion(
                assertion_id
            )
            if existing is not None:
                return existing
            if unit_of_work.field_operations.get_partner(partner_id) is None:
                raise FieldPerformanceConflict("performance_partner_not_found")
            return unit_of_work.field_performance.append_readiness_assertion(
                ReadinessAssertion(
                    assertion_id=assertion_id,
                    partner_id=partner_id,
                    requirement=requirement,
                    satisfied=satisfied,
                    source_domain=source_domain,
                    source_event_id=source_event_id,
                    evidence_reference=evidence_reference,
                    effective_at=effective_at,
                    expires_at=expires_at,
                    recorded_by_identity_id=subject.identity_id,
                    recorded_at=at,
                )
            )

    def recommend(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        kind: RecommendationKind,
        evidence_ids: tuple[UUID, ...],
        confidence_bps: int,
        reasoning: str,
        risks: tuple[str, ...],
        intelligence_domain: str,
        policy_version: str,
        idempotency_key: str,
        at: datetime,
    ) -> PerformanceRecommendation:
        with self._composition.unit_of_work() as unit_of_work:
            self._permission(unit_of_work, subject, "field_performance.recommend", at)
            recommendation_id = unit_of_work.field_performance.reserve(
                subject.identity_id,
                "recommendation.create",
                idempotency_key,
                f"{partner_id}:{kind}:{','.join(map(str, evidence_ids))}:{confidence_bps}:{reasoning}:{risks}:{intelligence_domain}:{policy_version}",
                uuid4(),
                at,
            )
            existing = unit_of_work.field_performance.get_recommendation(
                recommendation_id
            )
            if existing is not None:
                return existing
            evidence = unit_of_work.field_performance.evidence_by_ids(evidence_ids)
            if len(evidence) != len(set(evidence_ids)) or any(
                item.partner_id != partner_id for item in evidence
            ):
                raise FieldPerformanceConflict(
                    "performance_recommendation_evidence_invalid"
                )
            validate_recommendation(kind, evidence)
            return unit_of_work.field_performance.append_recommendation(
                PerformanceRecommendation(
                    recommendation_id=recommendation_id,
                    partner_id=partner_id,
                    kind=kind,
                    evidence_ids=evidence_ids,
                    confidence_bps=confidence_bps,
                    reasoning=reasoning,
                    risks=risks,
                    intelligence_domain=intelligence_domain,
                    policy_version=policy_version,
                    recommended_by_identity_id=subject.identity_id,
                    created_at=at,
                )
            )

    def own_view(
        self, subject: AuthorizationSubject, *, at: datetime
    ) -> RepresentativePerformanceView:
        with self._composition.unit_of_work() as unit_of_work:
            self._permission(unit_of_work, subject, "field_performance.read_own", at)
            partner = unit_of_work.field_operations.partner_for_identity(
                subject.identity_id
            )
            if partner is None:
                raise FieldPerformanceConflict("performance_partner_not_found")
            assertions = unit_of_work.field_performance.readiness_assertions(
                partner.partner_id, limit=100
            )
            return RepresentativePerformanceView(
                readiness=readiness(partner.partner_id, assertions, at=at),
                evidence=unit_of_work.field_performance.partner_evidence(
                    partner.partner_id, limit=100
                ),
                recommendations=unit_of_work.field_performance.partner_recommendations(
                    partner.partner_id, limit=100
                ),
            )

    def management_summary(
        self,
        subject: AuthorizationSubject,
        *,
        territory_id: UUID | None,
        at: datetime,
    ) -> TerritoryPerformanceSummary:
        with self._composition.unit_of_work() as unit_of_work:
            self._permission(
                unit_of_work, subject, "field_performance.management.read", at
            )
            return unit_of_work.field_performance.management_summary(
                territory_id, at=at
            )

    @staticmethod
    def _permission(
        unit_of_work: Any, subject: AuthorizationSubject, code: str, at: datetime
    ) -> None:
        if not unit_of_work.authorization.has_permission(
            subject.identity_id, code, at=at
        ):
            raise FieldPerformanceConflict("access_denied")
