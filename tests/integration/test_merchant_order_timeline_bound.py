from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, insert

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant_orders.application import MerchantOrderApplication
from BACKEND.merchant_orders.models import (
    MerchantOrderAction,
    MerchantOrderRecord,
    MerchantOrderView,
)
from BACKEND.merchant_preparation.application import MerchantPreparationApplication
from BACKEND.merchant_preparation.models import PreparationAction
from BACKEND.ordering.application import OrderingApplication
from BACKEND.ordering.models import BasketLine
from BACKEND.persistence.tables import (
    commerce_merchant_action_idempotency,
    commerce_order_evidence,
    commerce_order_idempotency,
    commerce_order_lines,
    commerce_order_outbox,
    commerce_order_preparations,
    commerce_order_rejections,
    commerce_order_timeline,
    commerce_orders,
    commerce_preparation_events,
    commerce_preparation_idempotency,
    identities,
    merchant_profiles,
    universal_catalogue_items,
)

NOW = datetime(2026, 8, 9, 10, tzinfo=UTC)
pytestmark = pytest.mark.integration
CUSTOMER = UUID("11111111-1111-4111-8111-111111111111")
MERCHANT_OWNER = UUID("22222222-2222-4222-8222-222222222222")
MERCHANT = UUID("33333333-3333-4333-8333-333333333333")
ITEM = UUID("44444444-4444-4444-8444-444444444444")
ACCESS_INTERACTION = UUID("55555555-5555-4555-8555-555555555555")


def subject(identity_id: UUID) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )


def cleanup(engine) -> None:
    with engine.begin() as connection:
        order_ids = connection.execute(
            commerce_orders.select()
            .with_only_columns(commerce_orders.c.order_id)
            .where(commerce_orders.c.merchant_id == MERCHANT)
        ).scalars()
        values = tuple(order_ids)
        if values:
            connection.execute(
                delete(commerce_preparation_events).where(
                    commerce_preparation_events.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_preparation_idempotency).where(
                    commerce_preparation_idempotency.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_preparations).where(
                    commerce_order_preparations.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_merchant_action_idempotency).where(
                    commerce_merchant_action_idempotency.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_outbox).where(
                    commerce_order_outbox.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_timeline).where(
                    commerce_order_timeline.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_rejections).where(
                    commerce_order_rejections.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_evidence).where(
                    commerce_order_evidence.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_order_lines).where(
                    commerce_order_lines.c.order_id.in_(values)
                )
            )
            connection.execute(
                delete(commerce_orders).where(commerce_orders.c.order_id.in_(values))
            )
        connection.execute(
            delete(commerce_order_idempotency).where(
                commerce_order_idempotency.c.customer_identity_id == CUSTOMER
            )
        )
        connection.execute(
            delete(universal_catalogue_items).where(
                universal_catalogue_items.c.item_id == ITEM
            )
        )
        connection.execute(
            delete(merchant_profiles).where(merchant_profiles.c.merchant_id == MERCHANT)
        )
        connection.execute(
            delete(identities).where(
                identities.c.identity_id.in_((CUSTOMER, MERCHANT_OWNER))
            )
        )


@pytest.fixture
def merchant_order_producer(postgres_engine):
    cleanup(postgres_engine)
    with postgres_engine.begin() as connection:
        for identity_id in (CUSTOMER, MERCHANT_OWNER):
            connection.execute(
                insert(identities).values(
                    identity_id=identity_id,
                    public_id=identity_id,
                    identity_type="rider",
                    status="active",
                    created_at=NOW,
                    updated_at=NOW,
                    version=1,
                )
            )
        connection.execute(
            insert(merchant_profiles).values(
                merchant_id=MERCHANT,
                owner_identity_id=MERCHANT_OWNER,
                legal_name="Timeline Merchant PLC",
                display_name="Timeline Merchant",
                kind="company",
                onboarding_source="self",
                state="approved",
                capability_code="merchant.general",
                market_code="ET-AA",
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(universal_catalogue_items).values(
                item_id=ITEM,
                merchant_id=MERCHANT,
                category_id=None,
                branch_id=None,
                kind="meal",
                name="Timeline meal",
                description=None,
                media=[],
                status="active",
                availability="available",
                visibility="public",
                tags=[],
                search_keywords=[],
                base_price_minor=1_000,
                currency="ETB",
                variant_contract_version=None,
                modifier_contract_version=None,
                source_item_id=None,
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    yield
    cleanup(postgres_engine)


def test_real_merchant_order_producer_has_hard_103_event_maximum(
    postgres_composition, merchant_order_producer
) -> None:
    del merchant_order_producer
    customer = subject(CUSTOMER)
    owner = subject(MERCHANT_OWNER)
    ordering = OrderingApplication(postgres_composition)
    orders = MerchantOrderApplication(postgres_composition)
    preparation = MerchantPreparationApplication(postgres_composition)

    created = ordering.create(
        customer,
        merchant_id=MERCHANT,
        lines=(BasketLine(item_id=ITEM, quantity=1, observed_version=1),),
        idempotency_key="timeline-order-create-0001",
        at=NOW,
        access_interaction_id=ACCESS_INTERACTION,
    )

    def projected() -> MerchantOrderView:
        return orders.detail(
            owner, merchant_id=MERCHANT, order_id=created.order_id, at=NOW
        )

    created_view = projected()
    assert MerchantOrderRecord.model_config["extra"] == "forbid"
    assert set(created.model_dump()) - set(created_view.order.model_dump()) == {
        "access_interaction_id",
        "availability_evaluation_id",
        "composition_hash",
        "customer_identity_id",
    }
    assert set(created_view.order.model_dump()) == {
        "created_at",
        "evidence_hash",
        "lines",
        "merchant_display_name",
        "merchant_id",
        "order_id",
        "pricing",
        "state",
        "version",
    }
    assert created.access_interaction_id == ACCESS_INTERACTION
    assert created.composition_hash is not None
    assert orders.list_orders(
        owner, merchant_id=MERCHANT, state=None, limit=25, at=NOW
    ) == (created_view,)
    assert [event.event_type for event in created_view.timeline] == [
        "commerce.order.created"
    ]

    accepted = orders.decide(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=1,
        action=MerchantOrderAction.ACCEPT,
        customer_reason_code=None,
        customer_message=None,
        internal_merchant_note=None,
        idempotency_key="timeline-order-accept-0001",
        at=NOW,
    )
    assert len(accepted.timeline) == 2
    replayed_acceptance = orders.decide(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=1,
        action=MerchantOrderAction.ACCEPT,
        customer_reason_code=None,
        customer_message=None,
        internal_merchant_note=None,
        idempotency_key="timeline-order-accept-0001",
        at=NOW,
    )
    assert replayed_acceptance == accepted
    assert len(projected().timeline) == 2

    started = preparation.command(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=2,
        action=PreparationAction.START,
        estimated_duration_minutes=30,
        progress_percent=None,
        delay_reason_code=None,
        delay_message=None,
        idempotency_key="timeline-preparation-start-0001",
        at=NOW,
    )
    assert len(started.order.timeline) == 3
    replayed_start = preparation.command(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=2,
        action=PreparationAction.START,
        estimated_duration_minutes=30,
        progress_percent=None,
        delay_reason_code=None,
        delay_message=None,
        idempotency_key="timeline-preparation-start-0001",
        at=NOW,
    )
    assert replayed_start == started
    assert len(projected().timeline) == 3

    progress_99 = None
    for progress_percent in range(1, 100):
        progress_99 = preparation.command(
            owner,
            merchant_id=MERCHANT,
            order_id=created.order_id,
            expected_version=progress_percent + 2,
            action=PreparationAction.UPDATE_PROGRESS,
            estimated_duration_minutes=None,
            progress_percent=progress_percent,
            delay_reason_code=None,
            delay_message=None,
            idempotency_key=f"timeline-progress-{progress_percent:02d}-0001",
            at=NOW,
        )
    assert progress_99 is not None
    assert len(progress_99.order.timeline) == 102
    assert (
        sum(
            event.event_type == "commerce.order.preparation_progress"
            for event in progress_99.order.timeline
        )
        == 99
    )
    assert [event.order_version for event in progress_99.order.timeline] == list(
        range(1, 103)
    )

    replayed_progress = preparation.command(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=101,
        action=PreparationAction.UPDATE_PROGRESS,
        estimated_duration_minutes=None,
        progress_percent=99,
        delay_reason_code=None,
        delay_message=None,
        idempotency_key="timeline-progress-99-0001",
        at=NOW,
    )
    assert replayed_progress == progress_99
    assert len(projected().timeline) == 102

    ready = preparation.command(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=102,
        action=PreparationAction.MARK_READY,
        estimated_duration_minutes=None,
        progress_percent=None,
        delay_reason_code=None,
        delay_message=None,
        idempotency_key="timeline-preparation-ready-0001",
        at=NOW,
    )
    assert ready.order.order.state.value == "ready_for_pickup"
    assert len(ready.order.timeline) == 103
    replayed_ready = preparation.command(
        owner,
        merchant_id=MERCHANT,
        order_id=created.order_id,
        expected_version=102,
        action=PreparationAction.MARK_READY,
        estimated_duration_minutes=None,
        progress_percent=None,
        delay_reason_code=None,
        delay_message=None,
        idempotency_key="timeline-preparation-ready-0001",
        at=NOW,
    )
    assert replayed_ready == ready

    final = projected()
    assert final.order.state.value == "ready_for_pickup"
    assert final.order.version == 103
    assert len(final.timeline) == 103
    assert Counter(event.event_type for event in final.timeline) == Counter(
        {
            "commerce.order.created": 1,
            "commerce.order.accepted": 1,
            "commerce.order.preparing": 1,
            "commerce.order.preparation_progress": 99,
            "commerce.order.ready_for_pickup": 1,
        }
    )
    assert [event.order_version for event in final.timeline] == list(range(1, 104))
