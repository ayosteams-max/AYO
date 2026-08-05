from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.merchant.engine import MerchantConflict, assert_program_open, readiness
from BACKEND.merchant.models import (
    MerchantKind,
    MerchantProfile,
    OnboardingSource,
    PartnerProgram,
    VerificationState,
)

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


def merchant() -> MerchantProfile:
    return MerchantProfile(
        owner_identity_id=uuid4(),
        legal_name="Addis Trading PLC",
        display_name="Addis Market",
        kind=MerchantKind.COMPANY,
        onboarding_source=OnboardingSource.SELF,
        capability_code="merchant.general",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )


def test_assisted_onboarding_never_makes_representative_the_owner() -> None:
    owner, representative = uuid4(), uuid4()
    value = MerchantProfile(
        owner_identity_id=owner,
        assisted_by_identity_id=representative,
        legal_name="Legal Merchant",
        display_name="Merchant",
        kind=MerchantKind.INDIVIDUAL,
        onboarding_source=OnboardingSource.REPRESENTATIVE,
        capability_code="merchant.general",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )
    assert value.owner_identity_id == owner
    assert value.assisted_by_identity_id == representative
    with pytest.raises(ValidationError, match="representative identity"):
        MerchantProfile(
            owner_identity_id=owner,
            legal_name="Legal Merchant",
            display_name="Merchant",
            kind=MerchantKind.INDIVIDUAL,
            onboarding_source=OnboardingSource.ASSISTED,
            capability_code="merchant.general",
            market_code="ET-AA",
            created_at=NOW,
            updated_at=NOW,
        )


def test_partner_program_window_and_limit_are_configuration_driven() -> None:
    program = PartnerProgram(
        code="founding.merchant",
        badge_label="Founding Merchant",
        capability_code="merchant.general",
        market_code="ET-AA",
        opens_at=NOW - timedelta(days=1),
        closes_at=NOW + timedelta(days=1),
        participant_limit=2,
    )
    assert_program_open(program, enrollment_count=1, at=NOW)
    with pytest.raises(MerchantConflict, match="partner_program_full"):
        assert_program_open(program, enrollment_count=2, at=NOW)
    with pytest.raises(MerchantConflict, match="partner_program_closed"):
        assert_program_open(program, enrollment_count=0, at=NOW + timedelta(days=2))


def test_readiness_is_deterministic_and_does_not_activate_commerce() -> None:
    result = readiness(
        merchant(),
        (VerificationState.APPROVED, VerificationState.SUBMITTED),
        catalogue_total=2,
        catalogue_ready=1,
    )
    assert result == (100, 50, 50, False)
    assert (
        readiness(
            merchant(),
            (VerificationState.APPROVED,),
            catalogue_total=1,
            catalogue_ready=1,
        )[3]
        is True
    )


def test_merchant_runtime_is_disabled_and_fails_closed_in_production() -> None:
    assert (
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None,
            DEBUG=False,
        ).MERCHANT_PLATFORM_ENABLED
        is False
    )
    with pytest.raises(
        ValidationError, match="Merchant Platform production activation"
    ):
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None,
            DEBUG=False,
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            MERCHANT_PLATFORM_ENABLED=True,
        )
