import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.persistence.tables import (
    active_rides,
    canonical_ride_requests,
    fare_calculations,
    fare_estimate_acceptances,
    fare_estimates,
    pricing_calculation_components,
    pricing_events,
    pricing_idempotency,
    pricing_outbox,
    pricing_policies,
)
from BACKEND.pricing.engine import PricingConflict
from BACKEND.pricing.models import (
    CalculationState,
    EstimateAcceptance,
    FareCalculation,
    FareEstimate,
    FinancialJourney,
    PricingPolicy,
    PricingPolicyStatus,
)


def _policy(row: Any) -> PricingPolicy:
    return PricingPolicy.model_validate(dict(row))


def _estimate(row: Any) -> FareEstimate:
    return FareEstimate.model_validate(dict(row))


class PostgresPricingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_policy(self, policy: PricingPolicy) -> PricingPolicy:
        if policy.status is not PricingPolicyStatus.DRAFT:
            raise PricingConflict("new_policy_must_be_draft")
        if policy.predecessor_policy_id is not None:
            predecessor = self.get_policy(policy.predecessor_policy_id)
            if predecessor is None or predecessor.policy_id == policy.policy_id:
                raise PricingConflict("policy_predecessor_invalid")
        self._connection.execute(insert(pricing_policies).values(**policy.model_dump()))
        return policy

    def get_policy(
        self, policy_id: UUID, *, lock: bool = False
    ) -> PricingPolicy | None:
        query = select(pricing_policies).where(
            pricing_policies.c.policy_id == policy_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _policy(row)

    def approve_policy(
        self, policy_id: UUID, checker_id: UUID, *, at: datetime
    ) -> PricingPolicy:
        current = self.get_policy(policy_id, lock=True)
        if current is None or current.status is not PricingPolicyStatus.DRAFT:
            raise PricingConflict("policy_not_approvable")
        if current.made_by_identity_id == checker_id:
            raise PricingConflict("maker_checker_required")
        changed = current.model_copy(
            update={
                "status": PricingPolicyStatus.APPROVED,
                "approved_by_identity_id": checker_id,
                "approved_at": at,
            }
        )
        self._connection.execute(
            update(pricing_policies)
            .where(pricing_policies.c.policy_id == policy_id)
            .values(
                status=changed.status.value,
                approved_by_identity_id=checker_id,
                approved_at=at,
            )
        )
        return changed

    def publish_policy(
        self, policy_id: UUID, publisher_id: UUID, *, at: datetime
    ) -> PricingPolicy:
        current = self.get_policy(policy_id, lock=True)
        if current is None or current.status is not PricingPolicyStatus.APPROVED:
            raise PricingConflict("policy_not_publishable")
        if current.approved_by_identity_id == publisher_id:
            raise PricingConflict("publication_separation_required")
        changed = current.model_copy(
            update={
                "status": PricingPolicyStatus.PUBLISHED,
                "published_at": at,
                "published_by_identity_id": publisher_id,
            }
        )
        self._connection.execute(
            update(pricing_policies)
            .where(pricing_policies.c.policy_id == policy_id)
            .values(
                status=changed.status.value,
                published_at=at,
                published_by_identity_id=publisher_id,
            )
        )
        return changed

    def ride_request_source(self, request_id: UUID) -> dict[str, Any] | None:
        row = (
            self._connection.execute(
                select(canonical_ride_requests).where(
                    canonical_ride_requests.c.request_id == request_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else dict(row)

    def active_ride_source(
        self, ride_id: UUID, *, lock: bool = False
    ) -> dict[str, Any] | None:
        query = select(active_rides).where(active_rides.c.ride_id == ride_id)
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else dict(row)

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        row = self._connection.execute(
            pg_insert(pricing_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(pricing_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(pricing_idempotency).where(
                    pricing_idempotency.c.actor_id == actor_id,
                    pricing_idempotency.c.operation == operation,
                    pricing_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise PricingConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def _validate_estimate_traceability(self, estimate: FareEstimate) -> None:
        trace = estimate.financial_traceability
        if trace.ride_request_id != estimate.ride_request_id:
            raise PricingConflict("financial_traceability_conflict")
        if trace.fare_estimate_id != estimate.estimate_id:
            raise PricingConflict("financial_traceability_conflict")

    def _validate_calculation_traceability(self, item: FareCalculation) -> None:
        ride = self.active_ride_source(item.ride_id)
        if ride is None:
            raise PricingConflict("financial_traceability_conflict")
        if ride["ride_request_id"] is None or ride["dispatch_handoff_id"] is None:
            raise PricingConflict("financial_traceability_conflict")
        if ride["assignment_id"] is None:
            raise PricingConflict("financial_traceability_conflict")
        estimate = self.get_estimate(item.estimate_id)
        if estimate is None:
            raise PricingConflict("financial_traceability_conflict")
        if estimate.ride_request_id != ride["ride_request_id"]:
            raise PricingConflict("financial_traceability_conflict")
        trace = item.financial_traceability
        if trace.ride_request_id != ride["ride_request_id"]:
            raise PricingConflict("financial_traceability_conflict")
        if trace.dispatch_handoff_id != ride["dispatch_handoff_id"]:
            raise PricingConflict("financial_traceability_conflict")
        if trace.assignment_id != ride["assignment_id"]:
            raise PricingConflict("financial_traceability_conflict")
        if trace.active_ride_id != item.ride_id:
            raise PricingConflict("financial_traceability_conflict")
        if trace.fare_estimate_id != item.estimate_id:
            raise PricingConflict("financial_traceability_conflict")
        if trace.fare_calculation_id != item.calculation_id:
            raise PricingConflict("financial_traceability_conflict")
        if item.predecessor_calculation_id is None:
            if trace.predecessor_fare_calculation_id is not None:
                raise PricingConflict("financial_traceability_conflict")
            return
        predecessor = self.get_calculation(item.predecessor_calculation_id)
        if predecessor is None:
            raise PricingConflict("financial_traceability_conflict")
        if predecessor.ride_id != item.ride_id:
            raise PricingConflict("financial_traceability_conflict")
        if predecessor.estimate_id != item.estimate_id:
            raise PricingConflict("financial_traceability_conflict")
        if predecessor.financial_traceability.ride_request_id != trace.ride_request_id:
            raise PricingConflict("financial_traceability_conflict")
        if (
            predecessor.financial_traceability.dispatch_handoff_id
            != trace.dispatch_handoff_id
        ):
            raise PricingConflict("financial_traceability_conflict")
        if predecessor.financial_traceability.assignment_id != trace.assignment_id:
            raise PricingConflict("financial_traceability_conflict")
        if predecessor.financial_traceability.active_ride_id != trace.active_ride_id:
            raise PricingConflict("financial_traceability_conflict")
        if (
            predecessor.financial_traceability.fare_estimate_id
            != trace.fare_estimate_id
        ):
            raise PricingConflict("financial_traceability_conflict")
        if trace.predecessor_fare_calculation_id != predecessor.calculation_id:
            raise PricingConflict("financial_traceability_conflict")

    def add_estimate(self, estimate: FareEstimate) -> FareEstimate:
        self._validate_estimate_traceability(estimate)
        self._connection.execute(
            insert(fare_estimates).values(**estimate.model_dump(mode="json"))
        )
        self._event(
            "fare_estimate",
            estimate.estimate_id,
            "pricing.estimate_created",
            estimate.created_at,
            estimate.correlation_id,
            estimate.causation_id,
            {
                "estimate_id": str(estimate.estimate_id),
                "ride_request_id": str(estimate.ride_request_id),
                "policy_version": estimate.policy_version,
                "currency": estimate.breakdown.currency,
                "translation_key": "pricing.estimate.created",
            },
            event_id=estimate.audit_reference,
        )
        return estimate

    def get_estimate(self, estimate_id: UUID) -> FareEstimate | None:
        row = (
            self._connection.execute(
                select(fare_estimates).where(
                    fare_estimates.c.estimate_id == estimate_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _estimate(row)

    def add_acceptance(
        self, acceptance: EstimateAcceptance, estimate: FareEstimate
    ) -> EstimateAcceptance:
        self._connection.execute(
            insert(fare_estimate_acceptances).values(**acceptance.model_dump())
        )
        self._event(
            "fare_estimate",
            estimate.estimate_id,
            "pricing.estimate_accepted",
            acceptance.accepted_at,
            estimate.correlation_id,
            estimate.estimate_id,
            {
                "estimate_id": str(estimate.estimate_id),
                "acceptance_id": str(acceptance.acceptance_id),
                "policy_version": acceptance.accepted_policy_version,
                "translation_key": "pricing.estimate.accepted",
            },
            event_id=acceptance.audit_reference,
        )
        return acceptance

    def get_acceptance_for_estimate(
        self, estimate_id: UUID
    ) -> EstimateAcceptance | None:
        row = (
            self._connection.execute(
                select(fare_estimate_acceptances).where(
                    fare_estimate_acceptances.c.estimate_id == estimate_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else EstimateAcceptance.model_validate(dict(row))

    def add_calculation(
        self, item: FareCalculation, correlation_id: UUID
    ) -> FareCalculation:
        self._validate_calculation_traceability(item)
        self._connection.execute(
            insert(fare_calculations).values(**item.model_dump(mode="json"))
        )
        event_type = (
            "pricing.corrected"
            if item.state is CalculationState.CORRECTED
            else "pricing.final_calculated"
        )
        translation_key = (
            "pricing.final.corrected"
            if item.state is CalculationState.CORRECTED
            else "pricing.final.calculated"
        )
        components = {
            "base": item.breakdown.base_minor,
            "distance": item.breakdown.distance_minor,
            "time": item.breakdown.time_minor,
            "minimum_adjustment": item.breakdown.minimum_adjustment_minor,
            "tax_placeholder": item.breakdown.tax_placeholder_minor,
            "driver_gross": item.breakdown.driver_gross_minor,
            "ayo_commission": item.breakdown.ayo_commission_minor,
            "driver_net_projection": item.breakdown.driver_net_projection_minor,
        }
        self._connection.execute(
            insert(pricing_calculation_components),
            [
                {
                    "component_id": uuid4(),
                    "calculation_id": item.calculation_id,
                    "component_type": kind,
                    "amount_minor": amount,
                    "currency": item.breakdown.currency,
                    "policy_version": item.policy_version,
                }
                for kind, amount in components.items()
            ],
        )
        if item.state is CalculationState.FINAL_CALCULATED:
            self._event(
                "fare_calculation",
                item.calculation_id,
                "pricing.final_inputs_received",
                item.calculated_at,
                correlation_id,
                item.estimate_id,
                {
                    "calculation_id": str(item.calculation_id),
                    "ride_id": str(item.ride_id),
                    "policy_version": item.policy_version,
                    "translation_key": "pricing.final.inputs_received",
                },
            )
        event_causation_id = item.predecessor_calculation_id or item.estimate_id
        self._event(
            "fare_calculation",
            item.calculation_id,
            event_type,
            item.calculated_at,
            correlation_id,
            event_causation_id,
            {
                "calculation_id": str(item.calculation_id),
                "ride_id": str(item.ride_id),
                "policy_version": item.policy_version,
                "translation_key": translation_key,
                "settlement_instruction_ready": False,
            },
            event_id=item.audit_reference,
        )
        return item

    def get_calculation(self, calculation_id: UUID) -> FareCalculation | None:
        row = (
            self._connection.execute(
                select(fare_calculations).where(
                    fare_calculations.c.calculation_id == calculation_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else FareCalculation.model_validate(dict(row))

    def financial_journey(self, ride_id: UUID) -> FinancialJourney | None:
        ride = self.active_ride_source(ride_id)
        if (
            ride is None
            or ride["ride_request_id"] is None
            or ride["dispatch_handoff_id"] is None
            or ride["assignment_id"] is None
        ):
            return None
        estimate_rows = self._connection.execute(
            select(fare_estimates)
            .where(fare_estimates.c.ride_request_id == ride["ride_request_id"])
            .order_by(fare_estimates.c.created_at, fare_estimates.c.estimate_id)
        ).mappings()
        calculation_rows = self._connection.execute(
            select(fare_calculations)
            .where(fare_calculations.c.ride_id == ride_id)
            .order_by(
                fare_calculations.c.calculated_at,
                fare_calculations.c.calculation_id,
            )
        ).mappings()
        estimates = tuple(_estimate(row) for row in estimate_rows)
        calculations = tuple(
            FareCalculation.model_validate(dict(row)) for row in calculation_rows
        )
        expected = (
            ride["ride_request_id"],
            ride["dispatch_handoff_id"],
            ride["assignment_id"],
            ride_id,
        )
        seen_calculations: set[UUID] = set()
        for item in calculations:
            if item.calculation_id in seen_calculations:
                raise PricingConflict("financial_traceability_conflict")
            seen_calculations.add(item.calculation_id)
            if (
                item.financial_traceability.ride_request_id,
                item.financial_traceability.dispatch_handoff_id,
                item.financial_traceability.assignment_id,
                item.financial_traceability.active_ride_id,
            ) != expected:
                raise PricingConflict("financial_traceability_conflict")
            if item.financial_traceability.fare_calculation_id != item.calculation_id:
                raise PricingConflict("financial_traceability_conflict")
            if item.financial_traceability.fare_estimate_id != item.estimate_id:
                raise PricingConflict("financial_traceability_conflict")
        estimate_ids = {item.estimate_id for item in estimates}
        if any(item.estimate_id not in estimate_ids for item in calculations):
            raise PricingConflict("financial_traceability_conflict")
        return FinancialJourney(
            active_ride_id=ride_id,
            ride_request_id=ride["ride_request_id"],
            dispatch_handoff_id=ride["dispatch_handoff_id"],
            assignment_id=ride["assignment_id"],
            fare_estimates=estimates,
            fare_calculations=calculations,
        )

    def _event(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        payload: dict[str, Any],
        *,
        event_id: UUID | None = None,
    ) -> None:
        event_id = event_id or uuid4()
        self._connection.execute(
            insert(pricing_events).values(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                schema_version=1,
                safe_payload=payload,
                occurred_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        )
        self._connection.execute(
            insert(pricing_outbox).values(
                message_id=uuid4(),
                event_id=event_id,
                event_type=event_type,
                safe_payload=payload,
                occurred_at=at,
                available_at=at,
                attempt_count=0,
            )
        )
