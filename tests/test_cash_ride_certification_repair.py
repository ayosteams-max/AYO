import hashlib
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.models import BookingConfirmation
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import IdentityType
from BACKEND.ledger.models import (
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict
from BACKEND.post_trip.cash_accounting import (
    CashAccountingInstruction,
    CashAccountingLedgerApplication,
    CashAccountingModel,
    CashAccountingPolicy,
    CashAccountingRecord,
    CashAccountingState,
    CashCollectionEvidence,
    CashEvidenceState,
    CashJournalLine,
    CashReconciliationApplication,
    CashReconciliationState,
    PolicyEnvironment,
    build_cash_accounting_instruction,
    build_cash_reconciliation_evidence,
)
from BACKEND.post_trip.engine import PostTripConflict
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
        reconciliation_clearing_account="platform_cash_clearing",
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


@pytest.mark.parametrize(
    "caller_controlled_field",
    (
        "platform_claim_minor",
        "driver_entitlement_minor",
        "tax_minor",
        "journal_lines",
        "debit_account",
        "credit_account",
        "balanced_alternative_journal",
        "accounting_model",
        "reconciliation_required",
        "input_hash",
        "policy_hash",
    ),
)
def test_accounting_post_api_rejects_caller_economic_instruction_fields(
    caller_controlled_field,
):
    parameters = inspect.signature(CashAccountingLedgerApplication.post).parameters
    assert "instruction" not in parameters
    assert caller_controlled_field not in parameters


def test_accounting_production_mode_is_trusted_composition_not_post_input():
    post_parameters = inspect.signature(CashAccountingLedgerApplication.post).parameters
    constructor_parameters = inspect.signature(
        CashAccountingLedgerApplication.__init__
    ).parameters
    assert "production" not in post_parameters
    assert "production" in constructor_parameters


class FakeAccountingPostTripRepository:
    def __init__(self, evidence_item, policy_item):
        self.evidence_item = evidence_item
        self.policy_item = policy_item

    def cash_collection_evidence(self, ride_id):
        return self.evidence_item if self.evidence_item.ride_id == ride_id else None

    def cash_accounting_policy(self, policy_id):
        return (
            self.policy_item
            if self.policy_item.accounting_policy_id == policy_id
            else None
        )


class FakeAccountingPricingRepository:
    def __init__(self, calculation_item):
        self.calculation_item = calculation_item

    def get_calculation(self, calculation_id):
        return (
            self.calculation_item
            if self.calculation_item.calculation_id == calculation_id
            else None
        )


class RejectUnexpectedLedgerUse:
    def __getattr__(self, name):
        raise AssertionError(f"ledger must not be reached: {name}")


class FakeAccountingUnit:
    def __init__(self, calculation_item, evidence_item, policy_item):
        self.pricing = FakeAccountingPricingRepository(calculation_item)
        self.post_trip = FakeAccountingPostTripRepository(evidence_item, policy_item)
        self.ledger = RejectUnexpectedLedgerUse()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_non_production_policy_cannot_reach_production_posting_boundary():
    item = calculation()
    evidence_item = evidence(item)
    policy_item = policy(CashAccountingModel.AGENT_NET_REMITTANCE)
    unit = FakeAccountingUnit(item, evidence_item, policy_item)
    application = CashAccountingLedgerApplication(
        FakeCashComposition(unit),
        book_id=uuid4(),
        account_ids={},
        production=True,
    )
    subject = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.SERVICE,
        actor_type=ActorType.SERVICE,
    )
    with pytest.raises(PostTripConflict, match="cash_accounting_policy_rejected"):
        application.post(
            subject,
            ride_id=item.ride_id,
            fare_calculation_id=item.calculation_id,
            evidence_id=evidence_item.evidence_id,
            accounting_policy_id=policy_item.accounting_policy_id,
            idempotency_key="cash-accounting-production-guard",
            correlation_id=item.ride_id,
            at=NOW,
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


def test_reconciliation_evidence_hash_rejects_amount_ride_and_record_tampering():
    value = build_cash_reconciliation_evidence(
        reconciliation_evidence_id=uuid4(),
        ride_id=uuid4(),
        accounting_instruction_id=uuid4(),
        accounting_policy_id=uuid4(),
        accounting_policy_version="cash.synthetic.agent.v1",
        original_accounting_journal_id=uuid4(),
        platform_claim_minor=20,
        currency="ETB",
        evidence_type="manual_remittance",
        source_classification="synthetic",
        authorized_actor_id=uuid4(),
        occurred_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    for field, changed in (
        ("platform_claim_minor", 19),
        ("ride_id", uuid4()),
        ("accounting_instruction_id", uuid4()),
        ("original_accounting_journal_id", uuid4()),
    ):
        with pytest.raises(ValidationError, match="hash does not bind"):
            value.model_copy(update={field: changed}).model_validate(
                {**value.model_dump(), field: changed}
            )


class FakeCashPostTripRepository:
    def __init__(self, record, accounting_policy):
        self.record = record
        self.accounting_policy = accounting_policy
        self.reconciliation_evidence = None
        self.fail_update_once = False

    def cash_accounting_record(self, ride_id):
        return self.record if self.record.ride_id == ride_id else None

    def cash_accounting_policy(self, policy_id):
        return (
            self.accounting_policy
            if self.accounting_policy.accounting_policy_id == policy_id
            else None
        )

    def add_cash_reconciliation_evidence(self, item):
        if (
            self.reconciliation_evidence is not None
            and self.reconciliation_evidence != item
        ):
            raise PostTripConflict("cash_reconciliation_evidence_conflict")
        self.reconciliation_evidence = item
        return item

    def update_cash_accounting_record(self, item, *, expected_version):
        if self.fail_update_once:
            self.fail_update_once = False
            raise PostTripConflict("simulated_state_update_failure")
        if self.record.version != expected_version:
            raise PostTripConflict("stale_cash_accounting_record")
        self.record = item.model_copy(update={"version": expected_version + 1})
        return self.record


class FakeCashLedgerRepository:
    def __init__(self, original):
        self.journals = {original.journal_id: original}
        self.idempotency = {}
        self.post_count = 0

    def get_journal(self, journal_id):
        return self.journals.get(journal_id)

    def reserve_idempotency(self, *, operation, key, payload, response_reference, **_):
        identity = (operation, key)
        digest = hashlib.sha256(repr(payload).encode()).hexdigest()
        existing = self.idempotency.get(identity)
        if existing is not None:
            if existing[0] != digest:
                raise PostTripConflict("idempotency_conflict")
            return existing[1]
        self.idempotency[identity] = (digest, response_reference)
        return response_reference

    def post_journal(self, journal):
        if journal.journal_id in self.journals:
            raise AssertionError("duplicate clearing journal")
        self.journals[journal.journal_id] = journal
        self.post_count += 1
        return journal


class FakeCashAuthorization:
    def __init__(self, allowed):
        self.allowed = allowed

    def has_permission(self, identity_id, permission, *, at):
        del identity_id, at
        return self.allowed and permission == "cash.reconciliation.execute"


class FakeCashUnit:
    def __init__(self, post_trip, ledger, authorization):
        self.post_trip = post_trip
        self.ledger = ledger
        self.authorization = authorization

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeCashComposition:
    def __init__(self, unit):
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def reconciliation_fixture(*, permission=True, production=False):
    accounting_policy = policy(CashAccountingModel.AGENT_NET_REMITTANCE)
    ride_id = uuid4()
    instruction_id = uuid4()
    original_journal_id = uuid4()
    receivable_id = uuid4()
    revenue_id = uuid4()
    clearing_id = uuid4()
    trace = LedgerTraceability(
        ride_request_id=uuid4(),
        dispatch_handoff_id=uuid4(),
        assignment_id=uuid4(),
        active_ride_id=ride_id,
        fare_estimate_id=uuid4(),
        fare_calculation_id=uuid4(),
    )
    original = LedgerJournal(
        journal_id=original_journal_id,
        book_id=uuid4(),
        business_event_type="ride.cash_accounting",
        business_event_id=instruction_id,
        operation="ride.cash_accounting.post",
        idempotency_key="cash-accounting-original",
        actor_identity_id=uuid4(),
        source_system="post_trip",
        reason_code="cash.policy_instruction.validated",
        traceability=trace,
        entries=(
            LedgerEntry(
                account_id=receivable_id,
                side=LedgerEntrySide.DEBIT,
                amount_minor=20,
                currency="ETB",
                line_index=1,
            ),
            LedgerEntry(
                account_id=revenue_id,
                side=LedgerEntrySide.CREDIT,
                amount_minor=20,
                currency="ETB",
                line_index=2,
            ),
        ),
        effective_at=NOW,
        recorded_at=NOW,
        correlation_id=ride_id,
        causation_id=instruction_id,
        audit_reference=uuid4(),
    )
    record = CashAccountingRecord(
        ride_id=ride_id,
        evidence_id=uuid4(),
        instruction_id=instruction_id,
        accounting_policy_id=accounting_policy.accounting_policy_id,
        accounting_policy_version=accounting_policy.accounting_policy_version,
        platform_claim_minor=20,
        driver_entitlement_minor=80,
        state=CashAccountingState.ACCOUNTING_POSTED,
        ledger_journal_id=original_journal_id,
        reconciliation_state=CashReconciliationState.PENDING,
        version=1,
    )
    post_trip = FakeCashPostTripRepository(record, accounting_policy)
    ledger = FakeCashLedgerRepository(original)
    unit = FakeCashUnit(post_trip, ledger, FakeCashAuthorization(permission))
    subject = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.SERVICE,
        actor_type=ActorType.SERVICE,
    )
    evidence_item = build_cash_reconciliation_evidence(
        reconciliation_evidence_id=uuid4(),
        ride_id=ride_id,
        accounting_instruction_id=instruction_id,
        accounting_policy_id=accounting_policy.accounting_policy_id,
        accounting_policy_version=accounting_policy.accounting_policy_version,
        original_accounting_journal_id=original_journal_id,
        platform_claim_minor=20,
        currency="ETB",
        evidence_type="manual_remittance",
        source_classification="synthetic",
        authorized_actor_id=subject.identity_id,
        occurred_at=NOW,
        correlation_id=ride_id,
        causation_id=original_journal_id,
    )
    application = CashReconciliationApplication(
        FakeCashComposition(unit),
        book_id=original.book_id,
        account_ids={
            "driver_remittance_receivable": receivable_id,
            "platform_cash_clearing": clearing_id,
        },
        production=production,
    )
    return application, subject, evidence_item, post_trip, ledger


def test_reconciliation_posts_obligation_bound_journal_and_replays_once():
    application, subject, item, post_trip, ledger = reconciliation_fixture()
    cleared = application.clear(
        subject,
        evidence=item,
        idempotency_key="cash-reconciliation-once",
        expected_version=1,
    )
    replay = application.clear(
        subject,
        evidence=item,
        idempotency_key="cash-reconciliation-once",
        expected_version=cleared.version,
    )
    journal = ledger.get_journal(cleared.clearing_journal_id)
    assert replay == cleared
    assert ledger.post_count == 1
    assert journal.business_event_type == "ride.cash_reconciliation"
    assert journal.predecessor_ledger_journal_id == item.original_accounting_journal_id
    assert journal.business_event_id == item.reconciliation_evidence_id
    assert post_trip.reconciliation_evidence == item


def test_reconciliation_recovers_exact_journal_after_state_update_failure():
    application, subject, item, post_trip, ledger = reconciliation_fixture()
    post_trip.fail_update_once = True
    with pytest.raises(PostTripConflict, match="simulated_state_update_failure"):
        application.clear(
            subject,
            evidence=item,
            idempotency_key="cash-reconciliation-recovery",
            expected_version=1,
        )
    recovered = application.clear(
        subject,
        evidence=item,
        idempotency_key="cash-reconciliation-recovery",
        expected_version=1,
    )
    assert recovered.reconciliation_state is CashReconciliationState.CLEARED
    assert ledger.post_count == 1


def test_reconciliation_rejects_missing_permission_and_unrelated_journal():
    application, subject, item, _, _ = reconciliation_fixture(permission=False)
    with pytest.raises(PostTripConflict, match="access_denied"):
        application.clear(
            subject,
            evidence=item,
            idempotency_key="cash-reconciliation-denied",
            expected_version=1,
        )
    application, subject, item, _, ledger = reconciliation_fixture()
    unrelated = uuid4()
    ledger.journals[unrelated] = next(iter(ledger.journals.values())).model_copy(
        update={"journal_id": unrelated}
    )
    tampered = item.model_copy(update={"original_accounting_journal_id": unrelated})
    with pytest.raises(PostTripConflict, match="evidence_invalid"):
        application.clear(
            subject,
            evidence=tampered,
            idempotency_key="cash-reconciliation-unrelated",
            expected_version=1,
        )


def test_synthetic_reconciliation_evidence_is_rejected_by_production_composition():
    application, subject, item, _, _ = reconciliation_fixture(production=True)
    with pytest.raises(PostTripConflict, match="evidence_invalid"):
        application.clear(
            subject,
            evidence=item,
            idempotency_key="cash-reconciliation-production-guard",
            expected_version=1,
        )


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
    assert "ledger_journal_id" not in SupportRideEvidenceProjection.model_fields
    assert "cash_accounting_journal_id" in SupportRideEvidenceProjection.model_fields
    assert (
        "cash_reconciliation_journal_id" in SupportRideEvidenceProjection.model_fields
    )
