import pytest

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.main import create_app


def test_active_ride_routes_disabled_by_default():
    app = create_app(Settings(ENVIRONMENT=AppEnvironment.TEST))
    assert not any("active-rides" in getattr(route, "path", "") for route in app.routes)


def test_active_ride_enabled_requires_explicit_secure_composition():
    with pytest.raises(RuntimeError, match="secure dependencies"):
        create_app(Settings(ENVIRONMENT=AppEnvironment.TEST, ACTIVE_RIDE_ENABLED=True))


def test_active_ride_production_activation_fails_closed():
    with pytest.raises(ValueError, match="separate approval"):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, ACTIVE_RIDE_ENABLED=True)
