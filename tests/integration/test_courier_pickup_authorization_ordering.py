from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text, update

from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import CourierPickupAction
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.tables import (
    commerce_courier_dispatch_requests,
    commerce_courier_pickups,
    courier_dispatch_assignments,
)
from tests.integration.test_courier_pickup_idempotency import (
    ACTOR,
    ASSIGNMENT,
    DISPATCH,
    KEY,
    MERCHANT_OWNER,
    NOW,
    PICKUP,
    ROLE,
    _cleanup_command_state,
    _effect_counts,
    _seed_command_state,
    _subject,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def authorization_ordering_state(postgres_engine):
    _seed_command_state(postgres_engine)
    try:
        yield
    finally:
        _cleanup_command_state(postgres_engine)


@pytest.mark.usefixtures("authorization_ordering_state")
def test_postgres_wrong_owner_is_rejected_before_permission_lookup(
    postgres_composition,
) -> None:
    application = CourierPickupApplication(postgres_composition)
    wrong_subject = _subject().model_copy(update={"identity_id": uuid4()})

    errors = []
    for pickup_id in (PICKUP, uuid4()):
        with pytest.raises(CourierPickupConflict) as captured:
            application.courier_command(
                wrong_subject,
                pickup_id=pickup_id,
                expected_version=1,
                action=CourierPickupAction.START_TRAVEL,
                idempotency_key="wrong-owner-postgres-0001",
                at=NOW,
            )
        errors.append(str(captured.value))
    assert errors == ["courier_pickup_unavailable", "courier_pickup_unavailable"]


@pytest.mark.usefixtures("authorization_ordering_state")
def test_postgres_replay_rechecks_ownership_and_exact_current_permission(
    postgres_engine,
    postgres_composition,
) -> None:
    application = CourierPickupApplication(postgres_composition)
    first = application.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW,
    )
    before = _effect_counts(postgres_engine)
    assert before == (1, 1, 1, 1, 1)

    wrong_subject = _subject().model_copy(update={"identity_id": uuid4()})
    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        CourierPickupApplication(
            PostgresRepositoryComposition(postgres_engine)
        ).courier_command(
            wrong_subject,
            pickup_id=PICKUP,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key=KEY,
            at=NOW + timedelta(days=1),
        )
    assert _effect_counts(postgres_engine) == before

    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM ayo.role_permissions "
                "WHERE role_id = CAST(:role_id AS uuid)"
            ),
            {"role_id": str(ROLE)},
        )
    with pytest.raises(CourierPickupConflict, match="^access_denied$"):
        CourierPickupApplication(
            PostgresRepositoryComposition(postgres_engine)
        ).courier_command(
            _subject(),
            pickup_id=PICKUP,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key=KEY,
            at=NOW + timedelta(days=1),
        )
    assert _effect_counts(postgres_engine) == before
    assert first.pickup.version == 2


@pytest.mark.usefixtures("authorization_ordering_state")
def test_postgres_assignment_change_has_no_route_application_gap(
    postgres_engine,
) -> None:
    replacement = MERCHANT_OWNER
    with postgres_engine.begin() as connection:
        connection.execute(
            update(commerce_courier_pickups)
            .where(commerce_courier_pickups.c.pickup_id == PICKUP)
            .values(assigned_courier_identity_id=replacement)
        )

    application = CourierPickupApplication(
        PostgresRepositoryComposition(postgres_engine)
    )
    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        application.courier_command(
            _subject(),
            pickup_id=PICKUP,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="assignment-changed-0001",
            at=NOW,
        )
    assert _effect_counts(postgres_engine) == (0, 0, 0, 0, 0)
    assert replacement != ACTOR


@pytest.mark.usefixtures("authorization_ordering_state")
@pytest.mark.parametrize("authority_loss", ["released", "stale_version"])
def test_postgres_obsolete_assignment_is_denied_before_command_side_effects(
    postgres_engine,
    authority_loss,
) -> None:
    with postgres_engine.begin() as connection:
        if authority_loss == "released":
            connection.execute(
                update(commerce_courier_dispatch_requests)
                .where(commerce_courier_dispatch_requests.c.dispatch_id == DISPATCH)
                .values(
                    state="waiting_for_courier",
                    active_assignment_id=None,
                    assigned_courier_identity_id=None,
                    version=2,
                )
            )
            connection.execute(
                update(courier_dispatch_assignments)
                .where(courier_dispatch_assignments.c.assignment_id == ASSIGNMENT)
                .values(
                    state="released_before_pickup",
                    version=2,
                    closed_at=NOW,
                    close_reason="courier_unavailable_before_pickup",
                )
            )
        else:
            connection.execute(
                update(courier_dispatch_assignments)
                .where(courier_dispatch_assignments.c.assignment_id == ASSIGNMENT)
                .values(version=2)
            )

    before = _effect_counts(postgres_engine)
    application = CourierPickupApplication(
        PostgresRepositoryComposition(postgres_engine)
    )
    for _ in range(2):
        with pytest.raises(
            CourierPickupConflict, match="^courier_pickup_assignment_invalid$"
        ):
            application.courier_command(
                _subject(),
                pickup_id=PICKUP,
                expected_version=1,
                action=CourierPickupAction.START_TRAVEL,
                idempotency_key=f"obsolete-{authority_loss}-0001",
                at=NOW,
            )
    assert _effect_counts(postgres_engine) == before
