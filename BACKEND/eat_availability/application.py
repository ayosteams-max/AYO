from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.catalogue.models import ItemAvailability, ItemStatus, ItemVisibility
from BACKEND.eat_availability.engine import availability_outcome, canonical_hash
from BACKEND.eat_availability.models import (
    EatAvailabilityEvaluation,
    EatAvailabilityPolicy,
    EatAvailabilityState,
)
from BACKEND.merchant.models import MerchantState


class ConfigureEatAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID
    area_reference: str = Field(min_length=8, max_length=200)
    coverage_reference: str = Field(min_length=8, max_length=200)
    state: EatAvailabilityState
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)
    effective_from: datetime
    effective_until: datetime | None = None


class EvaluateEatAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID
    merchant_version: int = Field(ge=1)
    merchant_open: bool
    area_reference: str = Field(min_length=8, max_length=200)
    coverage_reference: str = Field(min_length=8, max_length=200)
    item_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)


class EatAvailabilityApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def configure(
        self,
        subject: AuthorizationSubject,
        *,
        command: ConfigureEatAvailability,
        idempotency_key: str,
        correlation_id: UUID,
        request_id: UUID,
        expected_version: int | None = None,
        at: datetime | None = None,
    ) -> EatAvailabilityPolicy:
        instant = self._at(at)
        payload = command.model_dump(mode="json")
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "eat.availability.manage", at=instant
            ):
                raise PermissionError("eat_availability_manage_denied")
            prior = unit.eat_availability.reserve(
                actor_identity_id=subject.identity_id,
                operation="configure",
                key=idempotency_key,
                payload=payload,
                at=instant,
            )
            if prior:
                existing = unit.eat_availability.get(UUID(prior.rsplit("/", 1)[-1]))
                if existing is None:
                    raise RuntimeError("availability idempotency result unavailable")
                return existing
            current = unit.eat_availability.find(
                merchant_id=command.merchant_id,
                area_reference=command.area_reference,
            )
            if (current is None) != (expected_version is None):
                raise ValueError("availability_expected_version_required")
            if current is not None and current.version != expected_version:
                raise ValueError("availability_version_conflict")
            policy = EatAvailabilityPolicy(
                policy_id=current.policy_id if current else uuid4(),
                merchant_id=command.merchant_id,
                area_reference=command.area_reference,
                coverage_reference=command.coverage_reference,
                state=command.state,
                reason_code=command.reason_code,
                effective_from=command.effective_from,
                effective_until=command.effective_until,
                version=1 if current is None else current.version + 1,
                created_by_identity_id=(
                    subject.identity_id
                    if current is None
                    else current.created_by_identity_id
                ),
                created_at=instant if current is None else current.created_at,
                updated_at=instant,
            )
            saved = unit.eat_availability.put(policy, expected_version=expected_version)
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(subject.identity_id),
                    session_id=subject.session_id,
                    action="eat.availability.configure",
                    resource_type="eat_availability_policy",
                    resource_id=str(saved.policy_id),
                    outcome=AuditOutcome.SUCCESS,
                    correlation_id=correlation_id,
                    request_id=request_id,
                    source_module="eat_availability",
                    idempotency_key=idempotency_key,
                    safe_metadata={
                        "policy_version": saved.version,
                        "state_to": saved.state.value,
                    },
                )
            )
            unit.eat_availability.complete(
                actor_identity_id=subject.identity_id,
                operation="configure",
                key=idempotency_key,
                response_reference=f"eat_availability/{saved.policy_id}",
            )
            return saved

    def evaluate(
        self,
        subject: AuthorizationSubject,
        *,
        command: EvaluateEatAvailability,
        correlation_id: UUID,
        request_id: UUID,
        at: datetime | None = None,
    ) -> EatAvailabilityEvaluation:
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            merchant = unit.merchants.get_profile(command.merchant_id, lock=False)
            merchant_valid = (
                merchant is not None
                and merchant.state is MerchantState.APPROVED
                and merchant.version == command.merchant_version
            )
            items = tuple(
                unit.catalogue.get_item(item_id, lock=False)
                for item_id in command.item_ids
            )
            items_available = merchant_valid and all(
                item is not None
                and item.merchant_id == command.merchant_id
                and item.status is ItemStatus.ACTIVE
                and item.visibility is ItemVisibility.PUBLIC
                and item.availability is ItemAvailability.AVAILABLE
                for item in items
            )
            policy = unit.eat_availability.find(
                merchant_id=command.merchant_id,
                area_reference=command.area_reference,
            )
            coverage_matches = (
                policy is not None
                and policy.coverage_reference == command.coverage_reference
            )
            outcome, reason = availability_outcome(
                policy if coverage_matches and merchant_valid else None,
                merchant_open=command.merchant_open,
                items_available=items_available,
                at=instant,
            )
            evidence = {
                "policy_id": None if policy is None else str(policy.policy_id),
                "policy_version": None if policy is None else policy.version,
                "merchant_id": str(command.merchant_id),
                "merchant_version": command.merchant_version,
                "area_reference": command.area_reference,
                "coverage_reference": command.coverage_reference,
                "item_ids": sorted(str(value) for value in command.item_ids),
                "merchant_open": command.merchant_open,
                "outcome": outcome.value,
                "reason_code": reason,
                "evaluated_at": instant.isoformat(),
            }
            evaluation = EatAvailabilityEvaluation(
                policy_id=None if policy is None else policy.policy_id,
                policy_version=None if policy is None else policy.version,
                merchant_id=command.merchant_id,
                area_reference=command.area_reference,
                coverage_reference=command.coverage_reference,
                item_references=command.item_ids,
                merchant_open=command.merchant_open,
                outcome=outcome,
                reason_code=reason,
                evaluated_at=instant,
                evidence_hash=canonical_hash(evidence),
                correlation_id=correlation_id,
                request_id=request_id,
            )
            return unit.eat_availability.record_evaluation(evaluation)

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return instant.astimezone(UTC)
