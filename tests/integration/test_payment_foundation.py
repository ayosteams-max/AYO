from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy import insert as sa_insert

from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
    LifecycleCommandType,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.ledger.models import (
    LedgerAccount,
    LedgerAccountClass,
    LedgerBook,
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.engine import PaymentConflict
from BACKEND.payment.models import (
    PaymentAttemptState,
    PaymentIntent,
    PaymentMethodFamily,
)
from BACKEND.persistence.tables import (
    ledger_accounts,
    payment_attempts,
    payment_events,
    payment_outbox,
    permissions,
)
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.models import DataQuality, PricingPolicy, RouteMetrics
from tests.integration.test_dispatch_handoff_localization import (
    eligible_driver,
    ready_request,
)

pytestmark = [pytest.mark.integration]
NOW = datetime(2026, 7, 16, tzinfo=UTC)


def subject(identity_type: IdentityType, identity_id: UUID) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=identity_type,
        actor_type={
            IdentityType.RIDER: ActorType.RIDER,
            IdentityType.DRIVER: ActorType.DRIVER,
            IdentityType.STAFF: ActorType.STAFF,
            IdentityType.SERVICE: ActorType.SERVICE,
            IdentityType.ADMINISTRATOR: ActorType.ADMINISTRATOR,
            IdentityType.ANONYMOUS: ActorType.ANONYMOUS,
            IdentityType.MERCHANT: ActorType.SERVICE,
            IdentityType.SERVICE_PROVIDER: ActorType.SERVICE,
        }[identity_type],
    )


def create_identity(composition, identity_type: IdentityType) -> Identity:
    value = Identity(
        identity_type=identity_type,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    with composition.unit_of_work() as unit:
        return unit.identities.create(value)


def existing_identity_ref(identity_id: UUID, identity_type: IdentityType) -> Identity:
    return Identity(
        identity_id=identity_id,
        identity_type=identity_type,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def grant_permissions(composition, person: Identity, codes: tuple[str, ...]) -> None:
    role = Role(
        code=f"test.payment.{uuid4().hex[:20]}",
        description="Increment 9 payment test role",
        created_at=NOW,
    )
    with composition.unit_of_work() as unit:
        unit.authorization.create_role(role)
        for code in codes:
            permission_id = unit.connection.execute(
                select(permissions.c.permission_id).where(permissions.c.code == code)
            ).scalar_one_or_none()
            if permission_id is None:
                permission = Permission(
                    code=code,
                    description=f"Test grant for {code}",
                    created_at=NOW,
                )
                unit.authorization.create_permission(permission)
                permission_id = permission.permission_id
            unit.authorization.grant_permission(
                role.role_id,
                permission_id,
                granted_at=NOW,
            )
        unit.authorization.assign_role(
            RoleAssignment(
                identity_id=person.identity_id,
                role_id=role.role_id,
                assigned_by_identity_id=person.identity_id,
                assigned_at=NOW,
            )
        )


def route(distance=7000, duration=1200, at=NOW):
    return RouteMetrics(
        distance_meters=distance,
        duration_seconds=duration,
        observed_at=at,
        provider_id="synthetic.route",
        provider_version="v1",
        distance_source="approved_route_metric",
        duration_source="approved_route_metric",
        provenance_reference=f"approved-{uuid4()}",
        data_quality=DataQuality.APPROVED_SYNTHETIC,
    )


def published_policy(app, zone_id):
    maker = create_identity(app._composition, IdentityType.STAFF)
    checker = create_identity(app._composition, IdentityType.STAFF)
    publisher = create_identity(app._composition, IdentityType.STAFF)
    policy = PricingPolicy(
        policy_version=f"synthetic.{uuid4().hex}",
        service_zone_id=zone_id,
        service_type="immediate_standard",
        currency="ETB",
        base_fare_minor=1200,
        distance_rate_per_km_minor=450,
        time_rate_per_minute_minor=150,
        minimum_fare_minor=1500,
        commission_basis_points=2000,
        tax_placeholder_basis_points=0,
        rounding_increment_minor=5,
        effective_from=NOW - timedelta(days=1),
        made_by_identity_id=maker.identity_id,
        created_at=NOW,
    )
    app.create_policy(subject(IdentityType.STAFF, maker.identity_id), policy)
    app.approve_policy(
        subject(IdentityType.STAFF, checker.identity_id), policy.policy_id, at=NOW
    )
    return app.publish_policy(
        subject(IdentityType.STAFF, publisher.identity_id), policy.policy_id, at=NOW
    )


def completed_ride(composition, request):
    driver = eligible_driver(composition, 10)
    dispatch = ImmediateHandoffService(composition, policy_version="dispatch.v1")
    handoff = dispatch.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key=f"handoff-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = dispatch.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assignment_id = dispatch.respond(
        offer_id=offer.offer_id,
        driver_id=driver.driver_id,
        expected_version=1,
        accept=True,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    lifecycle = ActiveRideLifecycleApplication(composition.unit_of_work)
    ride = lifecycle.start_from_assignment(assignment_id, now=NOW)
    driver_actor = subject(IdentityType.DRIVER, driver.driver_id)
    service_actor = subject(IdentityType.SERVICE, uuid4())
    sequence = (
        (driver_actor, LifecycleCommandType.DRIVER_EN_ROUTE),
        (driver_actor, LifecycleCommandType.DRIVER_ARRIVED),
        (service_actor, LifecycleCommandType.PICKUP_CONFIRMED),
        (driver_actor, LifecycleCommandType.RIDE_STARTED),
        (driver_actor, LifecycleCommandType.DESTINATION_ARRIVED),
        (driver_actor, LifecycleCommandType.RIDE_COMPLETED),
    )
    version = 1
    for who, command in sequence:
        result = lifecycle.command(
            who,
            ride.ride_id,
            LifecycleCommand(
                command_id=uuid4(),
                expected_version=version,
                command_type=command,
                reason_code=f"test.{command.value}",
            ),
            now=NOW,
        )
        version = result["aggregate_version"]
    return ride, driver


def payable_context(postgres_composition):
    request, rider_subject = ready_request(postgres_composition)
    pricing = PricingApplication(postgres_composition)
    policy = published_policy(pricing, request.service_zone_id)
    estimate = pricing.estimate(
        rider_subject,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=route(),
        idempotency_key=f"estimate-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    pricing.accept(
        rider_subject,
        estimate.estimate_id,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    ride, _ = completed_ride(postgres_composition, request)
    calculation = pricing.final_calculation(
        subject(IdentityType.SERVICE, uuid4()),
        ride_id=ride.ride_id,
        estimate_id=estimate.estimate_id,
        metrics=route(distance=7100),
        idempotency_key=f"final-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        book = unit.ledger.add_book(
            LedgerBook(
                code=f"rides.etb.{uuid4().hex[:12]}",
                description="Ride financial postings in ETB",
                base_currency="ETB",
                created_at=NOW,
            )
        )
        rider_ar = LedgerAccount(
            book_id=book.book_id,
            code=f"rider.ar.{uuid4().hex[:8]}",
            name="Rider Receivable",
            account_class=LedgerAccountClass.ASSET,
            normal_side=LedgerEntrySide.DEBIT,
            currency="ETB",
            created_at=NOW,
        )
        revenue = LedgerAccount(
            book_id=book.book_id,
            code=f"ayo.revenue.{uuid4().hex[:8]}",
            name="AYO Fare Revenue",
            account_class=LedgerAccountClass.REVENUE,
            normal_side=LedgerEntrySide.CREDIT,
            currency="ETB",
            created_at=NOW,
        )
        unit.connection.execute(
            sa_insert(ledger_accounts), [rider_ar.model_dump(), revenue.model_dump()]
        )
        journal = unit.ledger.post_journal(
            LedgerJournal(
                book_id=book.book_id,
                business_event_type="pricing.final_calculated",
                business_event_id=calculation.calculation_id,
                operation="post_journal",
                idempotency_key=f"ledger-{uuid4()}",
                actor_identity_id=rider_subject.identity_id,
                source_system="pricing",
                reason_code="pricing.final_charge",
                traceability=LedgerTraceability(
                    ride_request_id=calculation.financial_traceability.ride_request_id,
                    dispatch_handoff_id=calculation.financial_traceability.dispatch_handoff_id,
                    assignment_id=calculation.financial_traceability.assignment_id,
                    active_ride_id=calculation.financial_traceability.active_ride_id,
                    fare_estimate_id=calculation.financial_traceability.fare_estimate_id,
                    fare_calculation_id=calculation.financial_traceability.fare_calculation_id,
                ),
                entries=(
                    LedgerEntry(
                        account_id=rider_ar.account_id,
                        side=LedgerEntrySide.DEBIT,
                        amount_minor=calculation.breakdown.rider_total_minor,
                        currency="ETB",
                        line_index=1,
                    ),
                    LedgerEntry(
                        account_id=revenue.account_id,
                        side=LedgerEntrySide.CREDIT,
                        amount_minor=calculation.breakdown.rider_total_minor,
                        currency="ETB",
                        line_index=2,
                    ),
                ),
                effective_at=NOW,
                recorded_at=NOW,
                correlation_id=uuid4(),
                causation_id=calculation.calculation_id,
                audit_reference=uuid4(),
            )
        )
    return {
        "ride": ride,
        "rider_subject": rider_subject,
        "rider_identity_id": rider_subject.identity_id,
        "calculation": calculation,
        "journal": journal,
    }


def test_increment9_payment_service_authority_and_state_matrix(
    postgres_composition,
) -> None:
    context = payable_context(postgres_composition)
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    support = create_identity(postgres_composition, IdentityType.STAFF)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        rider,
        (
            "payment.intent.create",
            "payment.intent.read_own",
            "payment.attempt.execute",
            "scheduled.support.handoff",
        ),
    )
    grant_permissions(
        postgres_composition,
        support,
        ("support.payment.read_status",),
    )
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "payment.callback.ingest",
            "payment.reconciliation.run",
            "payment.trace.read",
            "payment.attempt.execute",
        ),
    )
    payment = PaymentOrchestrationService(postgres_composition)
    rider_actor = subject(IdentityType.RIDER, rider.identity_id)
    service_actor = subject(IdentityType.SERVICE, service_identity.identity_id)
    support_actor = subject(IdentityType.STAFF, support.identity_id)

    intent = payment.create_payment_intent(
        rider_actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        ledger_journal_id=context["journal"].journal_id,
        rider_identity_id=rider.identity_id,
        passenger_identity_id=uuid4(),
        booker_identity_id=rider.identity_id,
        payer_identity_id=rider.identity_id,
        method=PaymentMethodFamily.CARD,
        idempotency_key=f"intent-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=context["calculation"].calculation_id,
        at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        third_party_booking_authorized=True,
    )
    assert intent.amount_minor == context["calculation"].breakdown.rider_total_minor

    with pytest.raises(PaymentConflict, match="ledger_journal_not_found"):
        payment.create_payment_intent(
            rider_actor,
            ride_id=context["ride"].ride_id,
            fare_calculation_id=context["calculation"].calculation_id,
            ledger_journal_id=uuid4(),
            rider_identity_id=rider.identity_id,
            passenger_identity_id=rider.identity_id,
            booker_identity_id=rider.identity_id,
            payer_identity_id=rider.identity_id,
            method=PaymentMethodFamily.CARD,
            idempotency_key=f"intent-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=context["calculation"].calculation_id,
            at=NOW,
        )

    with pytest.raises(PaymentConflict, match="third_party_booking_authority_required"):
        payment.create_payment_intent(
            rider_actor,
            ride_id=context["ride"].ride_id,
            fare_calculation_id=context["calculation"].calculation_id,
            ledger_journal_id=context["journal"].journal_id,
            rider_identity_id=rider.identity_id,
            passenger_identity_id=uuid4(),
            booker_identity_id=uuid4(),
            payer_identity_id=rider.identity_id,
            method=PaymentMethodFamily.CARD,
            idempotency_key=f"intent-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=context["calculation"].calculation_id,
            at=NOW,
        )

    attempt = payment.create_payment_attempt(
        rider_actor,
        payment_intent_id=intent.payment_intent_id,
        provider_code="provider.sample",
        provider_reference=f"ref-{uuid4().hex[:16]}",
        idempotency_key=f"attempt-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=intent.payment_intent_id,
        at=NOW,
    )
    submitted = payment.submit_provider_neutral_attempt(
        rider_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        idempotency_key=f"submit-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=1),
    )
    assert submitted.state is PaymentAttemptState.AUTHORIZATION_PENDING

    authorized = payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code="provider.sample",
        signature_fingerprint="a" * 32,
        callback=CallbackOutcome(
            outcome="authorized",
            provider_event_id="evt-1",
            payload={"status": "authorized"},
        ),
        idempotency_key=f"cb-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=2),
    )
    capture_pending = payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code="provider.sample",
        signature_fingerprint="a" * 32,
        callback=CallbackOutcome(
            outcome="capture_pending",
            provider_event_id="evt-2",
            payload={"status": "capture_pending"},
        ),
        idempotency_key=f"cb-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=3),
    )
    captured = payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code="provider.sample",
        signature_fingerprint="a" * 32,
        callback=CallbackOutcome(
            outcome="captured",
            provider_event_id="evt-3",
            payload={"status": "captured"},
        ),
        idempotency_key=f"cb-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=4),
    )
    assert authorized.state is PaymentAttemptState.AUTHORIZED
    assert capture_pending.state is PaymentAttemptState.CAPTURE_PENDING
    assert captured.state is PaymentAttemptState.CAPTURED

    with pytest.raises(PaymentConflict, match="payment_attempt_transition_invalid"):
        payment.ingest_authenticated_callback_envelope(
            service_actor,
            payment_attempt_id=attempt.payment_attempt_id,
            provider_code="provider.sample",
            signature_fingerprint="a" * 32,
            callback=CallbackOutcome(
                outcome="failed",
                provider_event_id="evt-4",
                payload={"status": "failed"},
            ),
            idempotency_key=f"cb-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW + timedelta(seconds=5),
        )

    status = payment.payment_status(
        support_actor,
        payment_intent_id=intent.payment_intent_id,
        at=NOW,
    )
    assert status.payment_intent.payment_intent_id == intent.payment_intent_id
    with pytest.raises(PaymentConflict, match="access_denied"):
        payment.create_payment_attempt(
            support_actor,
            payment_intent_id=intent.payment_intent_id,
            provider_code="provider.sample",
            provider_reference=f"ref-{uuid4().hex[:16]}",
            idempotency_key=f"attempt-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=intent.payment_intent_id,
            at=NOW,
        )


def test_increment9_payment_cash_and_reconciliation_and_history(
    postgres_composition,
) -> None:
    context = payable_context(postgres_composition)
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        rider,
        (
            "payment.intent.create",
            "payment.intent.read_own",
            "payment.attempt.execute",
        ),
    )
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "payment.callback.ingest",
            "payment.reconciliation.run",
            "payment.trace.read",
        ),
    )
    payment = PaymentOrchestrationService(postgres_composition)
    rider_actor = subject(IdentityType.RIDER, rider.identity_id)
    service_actor = subject(IdentityType.SERVICE, service_identity.identity_id)

    cash_intent = payment.create_payment_intent(
        rider_actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        ledger_journal_id=context["journal"].journal_id,
        rider_identity_id=rider.identity_id,
        passenger_identity_id=rider.identity_id,
        booker_identity_id=rider.identity_id,
        payer_identity_id=rider.identity_id,
        method=PaymentMethodFamily.CASH,
        idempotency_key=f"intent-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=context["calculation"].calculation_id,
        at=NOW,
    )
    cash_attempt = payment.create_payment_attempt(
        rider_actor,
        payment_intent_id=cash_intent.payment_intent_id,
        provider_code="cash.manual",
        provider_reference=f"cash-{uuid4().hex[:16]}",
        idempotency_key=f"attempt-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=cash_intent.payment_intent_id,
        at=NOW,
    )
    unknown = payment.submit_provider_neutral_attempt(
        rider_actor,
        payment_attempt_id=cash_attempt.payment_attempt_id,
        idempotency_key=f"submit-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=1),
    )
    assert unknown.state is PaymentAttemptState.OUTCOME_UNKNOWN

    replay = payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=cash_attempt.payment_attempt_id,
        provider_code="cash.manual",
        signature_fingerprint="a" * 32,
        callback=CallbackOutcome(
            outcome="captured",
            provider_event_id="cash-evt-1",
            payload={"driver_declared_cash": True, "collected_minor": 100},
        ),
        idempotency_key=f"cb-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=2),
    )
    assert replay.state is PaymentAttemptState.OUTCOME_UNKNOWN

    reconciled = payment.mark_reconciliation_required(
        service_actor,
        payment_attempt_id=cash_attempt.payment_attempt_id,
        reason_code="payment.provider_outage",
        correlation_id=uuid4(),
        at=NOW + timedelta(seconds=3),
    )
    assert reconciled.state is PaymentAttemptState.OUTCOME_UNKNOWN

    history_a = payment.payment_history_by_ride(
        service_actor,
        ride_id=context["ride"].ride_id,
        at=NOW,
    )
    history_b = payment.payment_history_by_ride(
        service_actor,
        ride_id=context["ride"].ride_id,
        at=NOW,
    )
    assert history_a.model_dump(mode="json") == history_b.model_dump(mode="json")

    with postgres_composition.unit_of_work() as unit:
        ledger_before = unit.ledger.get_journal(context["journal"].journal_id)
        attempt_count = unit.connection.execute(
            select(func.count()).select_from(payment_attempts)
        ).scalar_one()
        event_count = unit.connection.execute(
            select(func.count()).select_from(payment_events)
        ).scalar_one()
        outbox_count = unit.connection.execute(
            select(func.count()).select_from(payment_outbox)
        ).scalar_one()
    with postgres_composition.unit_of_work() as unit:
        ledger_after = unit.ledger.get_journal(context["journal"].journal_id)
    assert ledger_before == ledger_after
    assert attempt_count >= 1
    assert event_count == outbox_count


def test_increment9_payment_concurrency_idempotency_and_rollback(
    postgres_composition,
) -> None:
    context = payable_context(postgres_composition)
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    grant_permissions(
        postgres_composition,
        rider,
        (
            "payment.intent.create",
            "payment.intent.read_own",
            "payment.attempt.execute",
        ),
    )
    payment = PaymentOrchestrationService(postgres_composition)
    rider_actor = subject(IdentityType.RIDER, rider.identity_id)

    key = f"intent-same-{uuid4()}"
    first = payment.create_payment_intent(
        rider_actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        ledger_journal_id=context["journal"].journal_id,
        rider_identity_id=rider.identity_id,
        passenger_identity_id=rider.identity_id,
        booker_identity_id=rider.identity_id,
        payer_identity_id=rider.identity_id,
        method=PaymentMethodFamily.CARD,
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=context["calculation"].calculation_id,
        at=NOW,
    )
    second = payment.create_payment_intent(
        rider_actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        ledger_journal_id=context["journal"].journal_id,
        rider_identity_id=rider.identity_id,
        passenger_identity_id=rider.identity_id,
        booker_identity_id=rider.identity_id,
        payer_identity_id=rider.identity_id,
        method=PaymentMethodFamily.CARD,
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=context["calculation"].calculation_id,
        at=NOW,
    )
    assert first.payment_intent_id == second.payment_intent_id

    with pytest.raises(PaymentConflict, match="idempotency_conflict"):
        payment.create_payment_intent(
            rider_actor,
            ride_id=context["ride"].ride_id,
            fare_calculation_id=context["calculation"].calculation_id,
            ledger_journal_id=context["journal"].journal_id,
            rider_identity_id=rider.identity_id,
            passenger_identity_id=rider.identity_id,
            booker_identity_id=rider.identity_id,
            payer_identity_id=rider.identity_id,
            method=PaymentMethodFamily.CASH,
            idempotency_key=key,
            correlation_id=uuid4(),
            causation_id=context["calculation"].calculation_id,
            at=NOW,
        )

    def create_attempt(ref: str):
        return payment.create_payment_attempt(
            rider_actor,
            payment_intent_id=first.payment_intent_id,
            provider_code="provider.sample",
            provider_reference=ref,
            idempotency_key=f"attempt-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=first.payment_intent_id,
            at=NOW,
        )

    refs = [f"ref-{uuid4().hex[:12]}", f"ref-{uuid4().hex[:12]}"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result()
            for future in [
                pool.submit(create_attempt, refs[0]),
                pool.submit(create_attempt, refs[1]),
            ]
            if not future.exception()
        ]
    with postgres_composition.unit_of_work() as unit:
        attempts = unit.payments.list_attempts_for_intent(first.payment_intent_id)
    assert len(attempts) == 1
    assert len(outcomes) == 1

    with pytest.raises(RuntimeError), postgres_composition.unit_of_work() as unit:
        unit.payments.create_intent(
            PaymentIntent(
                ride_id=context["ride"].ride_id,
                rider_identity_id=rider.identity_id,
                passenger_identity_id=rider.identity_id,
                booker_identity_id=rider.identity_id,
                payer_identity_id=rider.identity_id,
                amount_minor=context["calculation"].breakdown.rider_total_minor,
                currency="ETB",
                payment_method_family=PaymentMethodFamily.CARD,
                traceability=first.traceability,
                created_at=NOW,
            )
        )
        raise RuntimeError("force rollback")
