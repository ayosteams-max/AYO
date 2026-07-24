from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.identity.compatibility_models import (
    AccountLifecycle,
    CanonicalSubject,
    IdentityAccount,
    LegacySemantic,
    SubjectKind,
)
from BACKEND.identity.legacy_inventory import legacy_reference_inventory
from BACKEND.persistence.tables import metadata


def test_legacy_inventory_covers_every_identity_reference() -> None:
    expected = {
        (table.name, column.name)
        for table in metadata.tables.values()
        for column in table.columns
        if "identity_id" in column.name
        or (table.name == "identities" and column.name == "identity_type")
    }
    inventory = legacy_reference_inventory()
    assert {(item.table, item.column) for item in inventory} == expected
    assert all(item.rationale for item in inventory)


def test_semantic_classification_preserves_business_and_authority_boundaries() -> None:
    semantics = {
        (item.table, item.column): item.semantic
        for item in legacy_reference_inventory()
    }
    assert (
        semantics[("dispatch_ride_requests", "rider_identity_id")]
        is LegacySemantic.BUSINESS_PARTICIPANT
    )
    assert (
        semantics[("identity_role_assignments", "identity_id")]
        is LegacySemantic.AUTHORIZATION_PRINCIPAL
    )
    assert (
        semantics[("wallet_accounts", "owner_identity_id")]
        is LegacySemantic.RESOURCE_OWNER
    )
    assert (
        semantics[("support_case_events", "actor_identity_id")]
        is LegacySemantic.AUDIT_ACTOR
    )


def test_account_lifecycle_is_explicit_and_closed_is_terminal() -> None:
    now = datetime.now(UTC)
    subject = CanonicalSubject(subject_kind=SubjectKind.HUMAN, created_at=now)
    account = IdentityAccount(
        subject_id=subject.subject_id,
        created_at=now,
        updated_at=now,
    )
    active = account.transition(AccountLifecycle.ACTIVE, at=now)
    locked = active.transition(AccountLifecycle.LOCKED, at=now)
    closed = locked.transition(AccountLifecycle.CLOSED, at=now)
    assert account.state is AccountLifecycle.PENDING_ACTIVATION
    assert closed.state is AccountLifecycle.CLOSED
    with pytest.raises(ValueError, match="Invalid account transition"):
        closed.transition(AccountLifecycle.ACTIVE, at=now)
    with pytest.raises(ValueError, match="Invalid account transition"):
        account.transition(AccountLifecycle.SUSPENDED, at=now)


def test_canonical_identifiers_are_opaque_and_independent() -> None:
    now = datetime.now(UTC)
    subject = CanonicalSubject(
        subject_id=uuid4(), subject_kind=SubjectKind.SERVICE, created_at=now
    )
    account = IdentityAccount(
        account_id=uuid4(),
        subject_id=subject.subject_id,
        created_at=now,
        updated_at=now,
    )
    assert account.account_id != subject.subject_id
