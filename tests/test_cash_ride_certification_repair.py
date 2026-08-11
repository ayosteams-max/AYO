import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.booking.models import BookingConfirmation
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.ledger.models import LedgerEntrySide
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict
from BACKEND.post_trip.cash_accounting import (
    CashAccountingInstruction,
    CashAccountingModel,
    CashAccountingPolicy,
    CashCollectionEvidence,
    CashEvidenceState,
    CashJournalLine,
    CashReconciliationState,
    PolicyEnvironment,
    build_cash_accounting_instruction,
)
from BACKEND.pricing.models import FareBreakdown
from BACKEND.support.ride_evidence import SupportRideEvidenceProjection

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def calculation(*, total: int = 100):
    return SimpleNamespace(
        ride_id=uuid4(),
        calculation_id=uuid4(),
        breakdown=FareBreakdown(
            currency="ETB",
            base_minor=total,
            distance_minor=0,
            time_minor=0,
            minimum_adjustment_minor=0,
            tax_placeholder_minor=0,
            rider_total_minor=total,
            driver_gross_minor=total,
            ayo_commission_minor=0,
            driver_net_projection_minor=total,
        ),
    )


def evidence(item) -> CashCollectionEvidence:
    return CashCollectionEvidence(
        ride_id=item.ride_id,
        rider_identity_id=uuid4(),
        driver_identity_id=uuid4(),
        fare_calculation_id=item.calculation_id,
        gross_cash_reported_minor=item.breakdown.rider_total_minor,
        state=CashEvidenceState.COLLECTION_CORROBORATED,
        evidence_policy_version="cash.evidence.synthetic.v1",
        rider_confirmation_id=uuid4(),
        driver_confirmation_id=uuid4(),
        evidence_hash="a" * 64,
        recorded_at=NOW,
    )


def policy(model: CashAccountingModel) -> CashAccountingPolicy:
    return CashAccountingPolicy(
        accounting_policy_version=f"cash.synthetic.{model.value}.v1",
        accounting_model=model,
        currency="ETB",
        effective_from=NOW - timedelta(days=1),
        effective_until=NOW + timedelta(days=1),
        environment=PolicyEnvironment.NON_PRODUCTION,
        service_type="immediate_standard",
        payment_method="cash",
        platform_claim_basis_points=(
            10_000 if model is CashAccountingModel.PRINCIPAL_GROSS else 2_000
        ),
        driver_entitlement_basis_points=8_000,
        tax_basis_points=0,
        principal_receivable_account=(
            "principal_gross_cash_receivable"
            if model is CashAccountingModel.PRINCIPAL_GROSS
            else None
        ),
        platform_claim_account=(
            "driver_remittance_receivable"
            if model is CashAccountingModel.AGENT_NET_REMITTANCE
            else None
        ),
        driver_entitlement_account=(
            "driver_earnings_payable"
            if model is CashAccountingModel.PRINCIPAL_GROSS
            else None
        ),
        platform_revenue_account="platform_service_fee_revenue",
        reconciliation_basis="synthetic.manual_remittance",
        policy_evidence_hash="b" * 64,
        approval_reference="NON-PRODUCTION-CTO-FIXTURE",
    )


def test_non_production_principal_instruction_is_balanced_and_explicit():
    item = calculation()
    instruction = build_cash_accounting_instruction(
        policy=policy(CashAccountingModel.PRINCIPAL_GROSS),
        calculation=item,
        evidence=evidence(item),
        at=NOW,
        production=False,
    )
    assert [
        (x.account_code, x.side, x.amount_minor) for x in instruction.journal_lines
    ] == [
        ("principal_gross_cash_receivable", LedgerEntrySide.DEBIT, 100),
        ("driver_earnings_payable", LedgerEntrySide.CREDIT, 80),
        ("platform_service_fee_revenue", LedgerEntrySide.CREDIT, 20),
    ]


def test_non_production_agent_records_only_platform_claim_without_driver_payable():
    item = calculation()
    instruction = build_cash_accounting_instruction(
        policy=policy(CashAccountingModel.AGENT_NET_REMITTANCE),
        calculation=item,
        evidence=evidence(item),
        at=NOW,
        production=False,
    )
    assert instruction.gross_cash_reported_minor == 100
    assert instruction.platform_claim_minor == 20
    assert [(x.account_code, x.amount_minor) for x in instruction.journal_lines] == [
        ("driver_remittance_receivable", 20),
        ("platform_service_fee_revenue", 20),
    ]


def test_non_production_policy_fails_closed_in_production():
    item = calculation()
    with pytest.raises(ValueError, match="non_production_cash_policy_rejected"):
        build_cash_accounting_instruction(
            policy=policy(CashAccountingModel.AGENT_NET_REMITTANCE),
            calculation=item,
            evidence=evidence(item),
            at=NOW,
            production=True,
        )


def test_unbalanced_cash_instruction_is_rejected_before_ledger():
    with pytest.raises(ValidationError, match="must be balanced"):
        CashAccountingInstruction(
            ride_id=uuid4(),
            fare_calculation_id=uuid4(),
            evidence_id=uuid4(),
            accounting_policy_id=uuid4(),
            accounting_policy_version="cash.synthetic.agent.v1",
            accounting_model=CashAccountingModel.AGENT_NET_REMITTANCE,
            gross_cash_reported_minor=100,
            platform_claim_minor=20,
            driver_entitlement_minor=80,
            tax_minor=0,
            journal_lines=(
                CashJournalLine(
                    account_code="driver_remittance_receivable",
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=20,
                ),
                CashJournalLine(
                    account_code="platform_service_fee_revenue",
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=19,
                ),
            ),
            reconciliation_required=True,
            input_hash="c" * 64,
            policy_hash="d" * 64,
        )


def test_cash_collection_evidence_never_implies_accounting_or_reconciliation():
    item = calculation()
    value = evidence(item)
    assert value.state is CashEvidenceState.COLLECTION_CORROBORATED
    assert CashReconciliationState.CLEARED.value not in value.model_dump_json()
    assert "platform_claim_minor" not in value.model_dump()


def test_booking_pricing_lineage_is_all_or_nothing():
    with pytest.raises(ValidationError, match="lineage must be complete"):
        BookingConfirmation(
            evidence_id=uuid4(),
            evidence_hash="a" * 64,
            quote_id=uuid4(),
            ride_request_id=uuid4(),
            fare_estimate_id=uuid4(),
            rider_identity_id=uuid4(),
            idempotency_key_hash="b" * 64,
            confirmed_at=NOW,
        )


class FakeDispatchRepository:
    def __init__(self, lineage):
        self.lineage = lineage
        self.handoff = None
        self.reserved = False

    def accepted_pricing_lineage(self, ride_request_id, *, at, require_current=True):
        del ride_request_id, at, require_current
        return self.lineage

    def reserve_idempotency(self, **kwargs):
        self.reserved = True
        return kwargs["response_reference"]

    def get_handoff(self, handoff_id):
        del handoff_id
        return self.handoff

    def ready_source(self, ride_request_id):
        return {
            "request_id": ride_request_id,
            "rider_identity_id": uuid4(),
            "service_type": "immediate_standard",
            "pickup_id": uuid4(),
            "destination_id": uuid4(),
            "service_zone_id": uuid4(),
            "zone_version": "addis.synthetic.v1",
            "decision_id": uuid4(),
            "version": 3,
            "validation_policy_version": "ride.synthetic.v1",
            "expires_at": NOW + timedelta(minutes=5),
        }

    def create_handoff(self, item):
        self.handoff = item
        return item


class FakeUnit:
    def __init__(self, repository):
        self.handoff_dispatch = repository

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeComposition:
    def __init__(self, repository):
        self.repository = repository

    def unit_of_work(self):
        return FakeUnit(self.repository)


def test_dispatch_fails_before_idempotency_without_accepted_pricing():
    repository = FakeDispatchRepository(None)
    service = ImmediateHandoffService(
        FakeComposition(repository), policy_version="dispatch.v1"
    )
    with pytest.raises(HandoffConflict, match="dispatch.accepted_pricing_required"):
        service.receive(
            ride_request_id=uuid4(),
            service_actor_id=uuid4(),
            idempotency_key="dispatch-pricing-required",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )
    assert repository.reserved is False


def test_dispatch_persists_exact_accepted_pricing_lineage():
    request_id = uuid4()
    estimate_id = uuid4()
    acceptance_id = uuid4()
    policy_id = uuid4()
    lineage_hash = hashlib.sha256(b"lineage").hexdigest()
    repository = FakeDispatchRepository(
        {
            "fare_estimate_id": estimate_id,
            "estimate_acceptance_id": acceptance_id,
            "policy_id": policy_id,
            "policy_version": "pricing.synthetic.v1",
            "pricing_lineage_hash": lineage_hash,
            "expires_at": NOW + timedelta(minutes=5),
        }
    )
    handoff = ImmediateHandoffService(
        FakeComposition(repository), policy_version="dispatch.v1"
    ).receive(
        ride_request_id=request_id,
        service_actor_id=uuid4(),
        idempotency_key="dispatch-pricing-present",
        correlation_id=request_id,
        causation_id=uuid4(),
        at=NOW,
    )
    assert handoff.fare_estimate_id == estimate_id
    assert handoff.estimate_acceptance_id == acceptance_id
    assert handoff.pricing_lineage_hash == lineage_hash


def test_support_projection_schema_excludes_sensitive_raw_fields():
    forbidden = {
        "candidate_rankings",
        "identity_documents",
        "session_artifacts",
        "raw_gps_history",
        "ledger_entries",
        "authorization_header",
        "provider_payload",
    }
    assert forbidden.isdisjoint(SupportRideEvidenceProjection.model_fields)
