from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.dispatch.scheduler import WorkerHealth
from BACKEND.main import ScheduledDispatchActivation, create_app
from BACKEND.observability import InMemoryMetricsSink, safe_event
from BACKEND.scheduled.integration_models import (
    CreateScheduledReservationCommand,
    NotificationKind,
    NotificationMessage,
    PassengerChannel,
)
from BACKEND.scheduled.notifications import LocalReservationNotificationPublisher
from BACKEND.scheduled.workers import (
    ClaimedCheckpoint,
    ScheduledWorkerCoordinator,
    ScheduledWorkerKind,
)

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def configuration(**changes):
    values = {
        "ENVIRONMENT": AppEnvironment.TEST,
        "DISPATCH_ENABLED": False,
        "SCHEDULED_DISPATCH_ENABLED": False,
    }
    values.update(changes)
    return Settings(**values)


def test_scheduled_routes_are_disabled_by_default_and_production_fails_closed():
    app = create_app(configuration())
    assert not any("/scheduled/" in path for path in app.openapi()["paths"])
    with pytest.raises(RuntimeError, match="explicit secure dependencies"):
        create_app(configuration(SCHEDULED_DISPATCH_ENABLED=True))
    with pytest.raises(ValueError, match="separate approval"):
        configuration(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            SCHEDULED_DISPATCH_ENABLED=True,
        )


def test_controlled_activation_registers_all_public_contracts():
    activation = ScheduledDispatchActivation(
        application=None,
        subject_resolver=None,
        authorization_enforcer=None,
        rate_limiter=None,
        metrics=InMemoryMetricsSink(),
    )
    app = create_app(
        configuration(SCHEDULED_DISPATCH_ENABLED=True),
        scheduled_dispatch=activation,
    )
    paths = set(app.openapi()["paths"])
    assert {
        "/api/scheduled/reservations",
        "/api/scheduled/reservations/{reservation_id}",
        "/api/scheduled/reservations/{reservation_id}/status",
        "/api/scheduled/reservations/{reservation_id}/cancel",
        "/api/scheduled/reservations/{reservation_id}/passenger/confirm",
        "/api/scheduled/reservations/{reservation_id}/passenger/decline",
        "/api/scheduled/reservations/{reservation_id}/driver/commitment",
        "/api/scheduled/reservations/{reservation_id}/pickup/verify",
        "/api/scheduled/reservations/{reservation_id}/support-handoff",
    } <= paths


def test_commands_forbid_identity_injection_and_unbounded_data():
    payload = {
        "pickup_place_id": "place.addis.bole",
        "destination_place_id": "place.addis.saris",
        "service_type": "ayo.go",
        "quote_id": uuid4(),
        "requested_pickup_at": NOW,
        "requested_timezone": "Africa/Addis_Ababa",
        "passenger_channel": PassengerChannel.IDENTITY,
        "booker_id": uuid4(),
    }
    with pytest.raises(ValueError):
        CreateScheduledReservationCommand.model_validate(payload)
    with pytest.raises(ValueError):
        CreateScheduledReservationCommand.model_validate(
            {**payload, "booker_id": None, "pickup_place_id": "x" * 129}
        )


def test_notification_adapter_is_idempotent_and_provider_neutral():
    message = NotificationMessage(
        event_id=uuid4(),
        reservation_id=uuid4(),
        recipient_reference="contact:opaque:1234",
        kind=NotificationKind.RESERVATION_ACCEPTED,
        occurred_at=NOW,
    )
    publisher = LocalReservationNotificationPublisher()
    publisher.publish(message)
    publisher.publish(message)
    assert list(publisher.delivered.values()) == [message]
    with pytest.raises(RuntimeError):
        publisher.publish(
            message.model_copy(update={"kind": NotificationKind.RESERVATION_CANCELLED})
        )


class FakeLock:
    def __init__(self, acquired=True):
        self.acquired = acquired

    @contextmanager
    def acquire(self):
        yield self.acquired


class FakeClaims:
    def __init__(self):
        self.item = ClaimedCheckpoint(
            checkpoint_id=uuid4(),
            reservation_id=uuid4(),
            kind=ScheduledWorkerKind.RECOVERY,
            attempt_count=1,
        )
        self.completed = []

    def claim(self, *args, **kwargs):
        del args, kwargs
        return [self.item]

    def complete(self, checkpoint_id, *, now):
        del now
        self.completed.append(checkpoint_id)


class Processor:
    def __init__(self, fails=False):
        self.fails = fails

    def process(self, checkpoint, *, now):
        del checkpoint, now
        if self.fails:
            raise RuntimeError("retryable")


def test_worker_is_bounded_overlap_safe_and_retry_safe():
    claims = FakeClaims()
    health = WorkerHealth()
    worker = ScheduledWorkerCoordinator(
        ScheduledWorkerKind.RECOVERY,
        FakeLock(),
        claims,
        Processor(),
        health=health,
        worker_id="scheduled-test",
        batch_limit=10,
    )
    result = worker.run_once(now=NOW)
    assert result.ran and result.completed == 1 and result.retried == 0
    assert health.snapshot().last_succeeded_at == NOW
    overlap = ScheduledWorkerCoordinator(
        ScheduledWorkerKind.RECOVERY,
        FakeLock(False),
        claims,
        Processor(),
        worker_id="scheduled-overlap",
    ).run_once(now=NOW)
    assert not overlap.ran and overlap.claimed == 0
    retry = ScheduledWorkerCoordinator(
        ScheduledWorkerKind.RECOVERY,
        FakeLock(),
        claims,
        Processor(fails=True),
        worker_id="scheduled-retry",
    ).run_once(now=NOW)
    assert retry.retried == 1 and retry.completed == 0


def test_structured_logging_rejects_contact_token_and_location_fields():
    logger = __import__("logging").getLogger(__name__)
    for field in ("access_token", "phone", "exact_location", "flight_booking"):
        with pytest.raises(ValueError):
            safe_event(logger, event="scheduled", outcome="denied", **{field: "x"})
