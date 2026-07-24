from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.identity.access_models import OwnershipRelationship
from BACKEND.identity.account_access_service import AccountAccessService
from BACKEND.identity.compatibility_models import AccountLifecycle
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.tables import (
    account_password_credentials,
    account_role_assignments,
    account_sessions,
    audit_events,
    canonical_subjects,
    identity_accounts,
    permissions,
    persistence_domain_events,
    persistence_outbox,
    role_permissions,
    roles,
)
from BACKEND.persistence.trace import TraceContext

pytestmark = [pytest.mark.integration, pytest.mark.identity_access]


def trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def seed_account(engine, *, state: str = "pending_activation") -> UUID:
    subject_id, account_id, now = uuid4(), uuid4(), datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(canonical_subjects).values(
                subject_id=subject_id, subject_kind="human", created_at=now, version=1
            )
        )
        connection.execute(
            insert(identity_accounts).values(
                account_id=account_id,
                subject_id=subject_id,
                state=state,
                created_at=now,
                updated_at=now,
                version=1,
                failed_attempt_count=0,
            )
        )
    return account_id


def seed_platform_admin(engine, account_id: UUID) -> None:
    now, role_id = datetime.now(UTC), uuid4()
    codes = [
        "identity.account.activate",
        "identity.account.suspend",
        "identity.account.unlock",
        "identity.account.close",
        "identity.roles.manage",
        "identity.sessions.revoke",
        "identity.ownership.override",
        "identity.account.force_credential_change",
        "identity.session.revoke_any",
        "identity.recovery.revoke",
        "identity.role.assign",
        "identity.role.remove",
    ]
    with engine.begin() as connection:
        connection.execute(
            insert(roles).values(
                role_id=role_id,
                code="platform_administrator",
                description="test administrator",
                system_managed=True,
                created_at=now,
                version=1,
            )
        )
        for code in codes:
            permission_id = uuid4()
            connection.execute(
                insert(permissions).values(
                    permission_id=permission_id,
                    code=code,
                    description=code,
                    created_at=now,
                )
            )
            connection.execute(
                insert(role_permissions).values(
                    role_id=role_id, permission_id=permission_id, granted_at=now
                )
            )
        connection.execute(
            insert(account_role_assignments).values(
                assignment_id=uuid4(),
                account_id=account_id,
                role_id=role_id,
                assigned_by_account_id=account_id,
                assigned_at=now,
                version=1,
            )
        )
        connection.execute(
            insert(roles).values(
                role_id=uuid4(),
                code="authenticated_user",
                description="test authenticated account",
                system_managed=True,
                created_at=now,
                version=1,
            )
        )


def activate(service: AccountAccessService, admin: UUID, account: UUID) -> None:
    service.transition_account(
        actor_account_id=admin,
        account_id=account,
        target=AccountLifecycle.ACTIVE,
        expected_version=1,
        reason="test_activation",
        idempotency_key=f"activate-{account}",
        trace=trace(),
    )


def test_password_authentication_is_account_native_atomic_and_retry_safe(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine)
    admin = seed_account(postgres_engine, state="active")
    seed_platform_admin(postgres_engine, admin)
    service = AccountAccessService(postgres_engine)
    credential = service.set_password(
        account_id=account,
        password="correct horse battery staple",
        idempotency_key="password-set-0001",
        trace=trace(),
    )
    assert credential.verifier != "correct horse battery staple"
    assert "$argon2id$" in credential.verifier
    activate(service, admin, account)
    first = service.authenticate(
        account_id=account,
        password="correct horse battery staple",
        client_reference="test-client",
        idempotency_key="authenticate-0001",
        trace=trace(),
    )
    second = service.authenticate(
        account_id=account,
        password="different password",
        client_reference="test-client",
        idempotency_key="authenticate-0001",
        trace=trace(),
    )
    assert first == second
    assert first.authenticated and first.session_id is not None
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(account_sessions)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
            >= 3
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_outbox)
            ).scalar_one()
            == connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
        )
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            >= 3
        )
    postgres_engine.dispose()
    assert (
        AccountAccessService(postgres_engine).validate_session(first.session_id)
        is not None
    )


def test_enumeration_resistance_and_failed_attempt_lock(postgres_engine) -> None:
    account = seed_account(postgres_engine, state="active")
    service = AccountAccessService(postgres_engine, failed_attempt_limit=2)
    service.set_password(
        account_id=account,
        password="correct horse battery staple",
        idempotency_key="password-set-0002",
        trace=trace(),
    )
    for index in range(2):
        result = service.authenticate(
            account_id=account,
            password="wrong-password-value",
            client_reference=None,
            idempotency_key=f"auth-denied-{index}",
            trace=trace(),
        )
        assert result.reason == "authentication_failed"
    missing = service.authenticate(
        account_id=uuid4(),
        password="wrong-password-value",
        client_reference=None,
        idempotency_key="auth-missing-0001",
        trace=trace(),
    )
    assert missing == result
    with postgres_engine.connect() as connection:
        row = (
            connection.execute(
                select(identity_accounts).where(
                    identity_accounts.c.account_id == account
                )
            )
            .mappings()
            .one()
        )
    assert row["state"] == "locked"
    assert row["failed_attempt_count"] == 2


def test_session_inactivity_rotation_replay_and_account_wide_state(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine, state="active")
    service = AccountAccessService(
        postgres_engine,
        absolute_lifetime=timedelta(hours=2),
        inactivity_timeout=timedelta(minutes=10),
    )
    service.set_password(
        account_id=account,
        password="correct horse battery staple",
        idempotency_key="password-set-0003",
        trace=trace(),
    )
    now = datetime.now(UTC)
    result = service.authenticate(
        account_id=account,
        password="correct horse battery staple",
        client_reference="bounded-device-reference",
        idempotency_key="authenticate-0003",
        trace=trace(),
        at=now,
    )
    assert result.session_id is not None
    assert (
        service.validate_session(result.session_id, at=now + timedelta(minutes=5))
        is not None
    )
    replacement = service.rotate_session(
        session_id=result.session_id,
        idempotency_key="rotate-session-0001",
        trace=trace(),
        at=now + timedelta(minutes=6),
    )
    assert (
        service.validate_session(result.session_id, at=now + timedelta(minutes=7))
        is None
    )
    revoked = service.revoke_all_sessions(
        actor_account_id=account,
        account_id=account,
        reason="user_requested",
        idempotency_key="revoke-all-0001",
        trace=trace(),
        at=now + timedelta(minutes=7),
    )
    assert replacement.session_id in revoked
    assert (
        service.validate_session(replacement.session_id, at=now + timedelta(minutes=8))
        is None
    )
    expiring = service.authenticate(
        account_id=account,
        password="correct horse battery staple",
        client_reference=None,
        idempotency_key="authenticate-expiry-0001",
        trace=trace(),
        at=now + timedelta(minutes=8),
    )
    assert expiring.session_id is not None
    assert (
        service.validate_session(expiring.session_id, at=now + timedelta(minutes=19))
        is None
    )


def test_rbac_deny_default_and_ownership_boundaries(postgres_engine) -> None:
    admin = seed_account(postgres_engine, state="active")
    target = seed_account(postgres_engine, state="active")
    seed_platform_admin(postgres_engine, admin)
    service = AccountAccessService(postgres_engine)
    assigned = service.assign_role(
        actor_account_id=admin,
        account_id=target,
        role_code="authenticated_user",
        idempotency_key="role-assign-0001",
        trace=trace(),
    )
    assert assigned.account_id == target
    assert (
        service.assign_role(
            actor_account_id=admin,
            account_id=target,
            role_code="authenticated_user",
            idempotency_key="role-assign-0001",
            trace=trace(),
        )
        == assigned
    )
    assert (
        service.effective_permissions(target, {"identity.account.close"}) == frozenset()
    )

    class Resolver:
        def relationship(self, *, account_id, resource_type, resource_id):
            del account_id, resource_type, resource_id
            return OwnershipRelationship.NONE

    assert not service.authorize_ownership(
        account_id=target, resource_type="fixture", resource_id="1", resolver=Resolver()
    ).allowed
    assert service.authorize_ownership(
        account_id=admin,
        resource_type="fixture",
        resource_id="1",
        resolver=Resolver(),
        request_administrative_override=True,
    ).allowed
    removed = service.remove_role(
        actor_account_id=admin,
        account_id=target,
        role_code="authenticated_user",
        reason="test_removal",
        idempotency_key="role-remove-0001",
        trace=trace(),
    )
    assert removed.revoked_at is not None
    assert (
        service.remove_role(
            actor_account_id=admin,
            account_id=target,
            role_code="authenticated_user",
            reason="test_removal",
            idempotency_key="role-remove-0001",
            trace=trace(),
        )
        == removed
    )


def test_concurrent_session_revocation_allows_one_state_change(postgres_engine) -> None:
    account = seed_account(postgres_engine, state="active")
    service = AccountAccessService(postgres_engine)
    service.set_password(
        account_id=account,
        password="correct horse battery staple",
        idempotency_key="password-set-0004",
        trace=trace(),
    )
    result = service.authenticate(
        account_id=account,
        password="correct horse battery staple",
        client_reference=None,
        idempotency_key="authenticate-0004",
        trace=trace(),
    )
    assert result.session_id is not None
    session_id = result.session_id

    def revoke(index: int):
        try:
            return service.revoke_session(
                actor_account_id=account,
                session_id=session_id,
                reason="user_requested",
                idempotency_key=f"revoke-session-{index}",
                trace=trace(),
            ).revoked_at
        except OptimisticConcurrencyError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(revoke, (1, 2)))
    assert any(value is not None for value in outcomes)
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(account_sessions)
                .where(account_sessions.c.revoked_at.is_not(None))
            ).scalar_one()
            == 1
        )


def test_injected_event_failure_rolls_back_credential(
    postgres_engine, monkeypatch
) -> None:
    account = seed_account(postgres_engine)
    service = AccountAccessService(postgres_engine)
    from BACKEND.persistence.kernel_repository import PostgresDomainEventRepository

    def fail(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("injected failure")

    monkeypatch.setattr(PostgresDomainEventRepository, "append", fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        service.set_password(
            account_id=account,
            password="correct horse battery staple",
            idempotency_key="password-rollback-1",
            trace=trace(),
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(account_password_credentials)
            ).scalar_one()
            == 0
        )
