import pytest

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.main import DispatchActivation, create_app
from BACKEND.observability import InMemoryMetricsSink


def configuration(**overrides):
    values = {
        "ENVIRONMENT": AppEnvironment.TEST,
        "DISPATCH_ENABLED": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_dispatch_is_disabled_by_default_and_absent_from_routes() -> None:
    app = create_app(configuration())
    paths = set(app.openapi()["paths"])
    assert "/api/dispatch/rides" not in paths
    assert "/api/internal/dispatch/workers/recovery/health" not in paths


def test_enabled_dispatch_requires_explicit_secure_dependencies() -> None:
    with pytest.raises(RuntimeError, match="secure activation dependencies"):
        create_app(configuration(DISPATCH_ENABLED=True))


def test_production_dispatch_activation_is_configuration_blocked() -> None:
    with pytest.raises(ValueError, match="separate recorded approval"):
        configuration(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            DISPATCH_ENABLED=True,
        )


def test_controlled_test_activation_registers_public_and_internal_routes() -> None:
    activation = DispatchActivation(
        application=None,
        subject_resolver=None,
        authorization_enforcer=None,
        rate_limiter=None,
        recovery_coordinator=None,
        outbox_worker=None,
        recovery_health=None,
        outbox_health=None,
        metrics=InMemoryMetricsSink(),
    )
    app = create_app(configuration(DISPATCH_ENABLED=True), dispatch=activation)
    paths = set(app.openapi()["paths"])
    assert "/api/dispatch/rides" in paths
    assert "/api/internal/dispatch/workers/recovery/health" in paths
