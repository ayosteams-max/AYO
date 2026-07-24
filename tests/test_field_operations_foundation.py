from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.field_operations.engine import (
    FieldOperationsConflict,
    assert_assignment_authority,
)
from BACKEND.field_operations.models import (
    ActivityKind,
    FieldPartner,
    PartnerAssignment,
    PartnerRole,
    PartnerStatus,
    Territory,
    VerificationStatus,
)

NOW = datetime(2026, 7, 21, 8, tzinfo=UTC)


def partner(*, active: bool = True, verified: bool = True) -> FieldPartner:
    return FieldPartner(
        public_partner_id="AYO-FP-ABCDEF12",
        identity_id=uuid4(),
        photo_reference="opaque-photo-reference",
        qr_reference_hash="a" * 64,
        verification_status=VerificationStatus.VERIFIED
        if verified
        else VerificationStatus.PENDING,
        status=PartnerStatus.ACTIVE if active else PartnerStatus.INACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def test_configurable_role_and_active_assignment_authorize_only_declared_activity() -> (
    None
):
    value = partner()
    role = PartnerRole(
        code="merchant_success_advisor",
        public_title="Merchant Success Advisor",
        allowed_activities=(ActivityKind.BUSINESS_VISITED,),
    )
    assignment = PartnerAssignment(
        partner_id=value.partner_id,
        role_id=role.role_id,
        territory_id=uuid4(),
        starts_at=NOW - timedelta(hours=1),
    )
    assert_assignment_authority(
        value, assignment, role, activity=ActivityKind.BUSINESS_VISITED, at=NOW
    )
    with pytest.raises(FieldOperationsConflict, match="field_activity_not_permitted"):
        assert_assignment_authority(
            value, assignment, role, activity=ActivityKind.DRIVER_RECRUITED, at=NOW
        )


def test_inactive_unverified_or_expired_partner_fails_closed() -> None:
    role = PartnerRole(
        code="quality_advisor",
        public_title="Quality Advisor",
        allowed_activities=(ActivityKind.QUALITY_CHECKED,),
    )
    for value, assignment in (
        (
            partner(active=False),
            PartnerAssignment(
                partner_id=uuid4(),
                role_id=role.role_id,
                territory_id=uuid4(),
                starts_at=NOW,
            ),
        ),
        (
            partner(verified=False),
            PartnerAssignment(
                partner_id=uuid4(),
                role_id=role.role_id,
                territory_id=uuid4(),
                starts_at=NOW,
            ),
        ),
        (
            partner(),
            PartnerAssignment(
                partner_id=uuid4(),
                role_id=role.role_id,
                territory_id=uuid4(),
                starts_at=NOW - timedelta(days=2),
                ends_at=NOW - timedelta(days=1),
            ),
        ),
    ):
        with pytest.raises(FieldOperationsConflict):
            assert_assignment_authority(
                value, assignment, role, activity=ActivityKind.QUALITY_CHECKED, at=NOW
            )


def test_territories_are_structured_and_titles_are_not_hardcoded() -> None:
    territory = Territory(
        market_code="ET-AA",
        region="Addis Ababa",
        city="Addis Ababa",
        district="Bole",
        name="Bole North",
    )
    assert territory.city == "Addis Ababa"
    with pytest.raises(ValidationError):
        PartnerRole(code="x", public_title="Temp", allowed_activities=())


def test_production_activation_is_prohibited() -> None:
    with pytest.raises(
        ValueError, match="production activation requires separate approval"
    ):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            FIELD_OPERATIONS_PLATFORM_ENABLED=True,
        )


def test_source_guards_preserve_account_and_financial_boundaries() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    source = "\n".join(
        (root / "BACKEND" / "field_operations" / name).read_text(encoding="utf-8")
        for name in ("models.py", "application.py", "engine.py")
    )
    prohibited = (
        "wallet",
        "payroll",
        "tax_withholding",
        "incentive_amount",
        "password",
        "legal_agreement_approved",
    )
    assert not any(value in source.lower() for value in prohibited)
    migration = (
        root
        / "database"
        / "migrations"
        / "versions"
        / "20260721_0041_field_operations_foundation.py"
    ).read_text(encoding="utf-8")
    assert "field_operations_idempotency" in migration
    assert "field_operations_events" in migration
    assert (
        "DROP"
        not in migration.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    )
