from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import CourierPickupAction
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.routes.courier_pickup import _courier_command_result
from tests.integration.test_courier_pickup_idempotency import (
    KEY,
    NOW,
    PICKUP,
    ROLE,
    _cleanup_command_state,
    _effect_counts,
    _seed_command_state,
    _subject,
)


@pytest.fixture
def api_contract_state(postgres_engine):
    _seed_command_state(postgres_engine)
    try:
        yield
    finally:
        _cleanup_command_state(postgres_engine)


@pytest.mark.usefixtures("api_contract_state")
def test_persisted_replay_maps_to_the_exact_minimized_public_body(
    postgres_engine,
    postgres_composition,
) -> None:
    first = CourierPickupApplication(postgres_composition).courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW,
        correlation_id=None,
        causation_id=None,
    )
    first_public = _courier_command_result(first).model_dump_json()
    before = _effect_counts(postgres_engine)

    fresh_composition = PostgresRepositoryComposition(postgres_engine)
    replay = CourierPickupApplication(fresh_composition).courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW + timedelta(days=1),
        correlation_id=None,
        causation_id=None,
    )
    replay_public = _courier_command_result(replay).model_dump_json()

    assert replay_public == first_public
    assert _effect_counts(postgres_engine) == before == (1, 1, 1, 1, 1)
    for prohibited in (
        "dispatch_id",
        "assignment_id",
        "merchant_id",
        "assigned_courier_identity_id",
        "events",
        "evidence",
        "correlation_id",
        "causation_id",
    ):
        assert prohibited not in replay_public


@pytest.mark.usefixtures("api_contract_state")
def test_replay_rechecks_current_permission_without_disclosing_snapshot(
    postgres_engine,
    postgres_composition,
) -> None:
    app = CourierPickupApplication(postgres_composition)
    app.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW,
        correlation_id=None,
        causation_id=None,
    )
    before = _effect_counts(postgres_engine)
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM ayo.auth_role_permissions "
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
            correlation_id=None,
            causation_id=None,
        )
    assert _effect_counts(postgres_engine) == before


@pytest.mark.usefixtures("api_contract_state")
def test_cross_courier_and_missing_pickup_are_indistinguishable(
    postgres_composition,
) -> None:
    application = CourierPickupApplication(postgres_composition)
    wrong_subject = _subject().model_copy(update={"identity_id": uuid4()})
    errors = []
    for pickup_id in (PICKUP, uuid4()):
        with pytest.raises(CourierPickupConflict) as captured:
            application.courier_detail(wrong_subject, pickup_id=pickup_id)
        errors.append(str(captured.value))
    assert errors == ["courier_pickup_unavailable", "courier_pickup_unavailable"]
