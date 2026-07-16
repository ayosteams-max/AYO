from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.dispatch.handoff import EligibleDriverInput, rank_candidates
from BACKEND.localization.models import (
    LanguagePackManifest,
    LanguagePreference,
    TextDirection,
    TranslationKey,
    WordingClass,
    message_ref,
    resolve_available_language,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def candidate(cost: int, **changes):
    vehicle = uuid4()
    values = dict(
        driver_id=uuid4(),
        vehicle_id=vehicle,
        authorized_vehicle_id=vehicle,
        account_active=True,
        eligibility_status="eligible",
        eligibility_expires_at=NOW + timedelta(days=1),
        vehicle_approved=True,
        supported_services=frozenset({"immediate_standard"}),
        availability="available",
        availability_observed_at=NOW,
        pickup_cost_seconds=cost,
        eligibility_policy_version="identity.v1",
    )
    values.update(changes)
    return EligibleDriverInput(**values)


def test_pickup_speed_is_primary_and_ineligible_inputs_fail_closed() -> None:
    slower = candidate(80)
    fastest = candidate(20)
    stale = candidate(1, availability_observed_at=NOW - timedelta(minutes=2))
    substituted = candidate(2, authorized_vehicle_id=uuid4())
    ranked = rank_candidates(
        [slower, stale, fastest, substituted], now=NOW, max_age_seconds=45
    )
    assert [x.driver_id for x in ranked] == [fastest.driver_id, slower.driver_id]


def test_global_language_tags_rtl_and_fallback_cycle() -> None:
    preference = LanguagePreference(
        identity_id=uuid4(),
        preferred_language="ar-EG",
        device_language="en-AU",
        fallback_chain=("en", "am"),
        updated_at=NOW,
    )
    assert preference.preferred_language == "ar-EG"
    manifest = LanguagePackManifest(
        language_tag="ar",
        pack_version="pack.v1",
        direction=TextDirection.RIGHT_TO_LEFT,
        date_format_profile="cldr.ar",
        number_format_profile="cldr.ar",
        currency_format_profile="cldr.ar",
    )
    assert manifest.direction is TextDirection.RIGHT_TO_LEFT
    with pytest.raises(ValidationError, match="cycle"):
        LanguagePreference(
            identity_id=uuid4(),
            preferred_language="en",
            fallback_chain=("am", "EN"),
            updated_at=NOW,
        )
    with pytest.raises(ValidationError):
        LanguagePreference(
            identity_id=uuid4(),
            preferred_language="not_a_tag",
            fallback_chain=(),
            updated_at=NOW,
        )
    selected, missing = resolve_available_language(preference, frozenset({"am"}))
    assert selected == "am"
    assert missing == ("ar-EG", "en")


def test_critical_wording_requires_human_review_and_reason_is_language_neutral() -> (
    None
):
    with pytest.raises(ValidationError, match="human review"):
        TranslationKey(
            key="safety.pickup.warning",
            version="v1",
            wording_class=WordingClass.SAFETY,
            human_review_required=False,
        )
    ref = message_ref("dispatch.searching")
    assert ref.translation_key == "dispatch.search.nearby_driver"
    with pytest.raises(KeyError, match="Missing"):
        message_ref("dispatch.unknown")
