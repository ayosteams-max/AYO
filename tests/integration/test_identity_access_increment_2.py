from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.identity.account_access_service import AccountAccessService
from BACKEND.persistence.account_access_repository import AccountAccessConflict
from BACKEND.persistence.kernel_repository import PostgresDomainEventRepository
from BACKEND.persistence.tables import (
    account_recovery_tokens,
    account_role_assignments,
    audit_events,
    authentication_origin_windows,
    canonical_subjects,
    identity_accounts,
    identity_security_bootstrap,
    permissions,
    persistence_domain_events,
    persistence_outbox,
    role_permissions,
    roles,
)
from BACKEND.persistence.trace import TraceContext

pytestmark = [pytest.mark.integration, pytest.mark.identity_access]
PEPPER = b"increment-2-test-pepper-material-32-bytes-minimum"
BOOTSTRAP_SECRET = "one-time-bootstrap-secret-with-sufficient-entropy"


def trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def seed_account(engine, *, state: str = "active"):
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
                credential_change_required=False,
            )
        )
    return account_id


def seed_security_roles(engine, admin_account_id=None) -> None:
    now, admin_role_id, user_role_id = datetime.now(UTC), uuid4(), uuid4()
    codes = [
        "identity.account.activate",
        "identity.account.suspend",
        "identity.account.unlock",
        "identity.account.close",
        "identity.account.force_credential_change",
        "identity.session.revoke_any",
        "identity.recovery.revoke",
        "identity.role.assign",
        "identity.role.remove",
        "identity.ownership.override",
    ]
    with engine.begin() as connection:
        connection.execute(
            insert(roles).values(
                role_id=admin_role_id,
                code="platform_administrator",
                description="test administrator",
                system_managed=True,
                created_at=now,
                version=1,
            )
        )
        connection.execute(
            insert(roles).values(
                role_id=user_role_id,
                code="authenticated_user",
                description="test user",
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
                    role_id=admin_role_id, permission_id=permission_id, granted_at=now
                )
            )
        if admin_account_id is not None:
            connection.execute(
                insert(account_role_assignments).values(
                    assignment_id=uuid4(),
                    account_id=admin_account_id,
                    role_id=admin_role_id,
                    assigned_by_account_id=admin_account_id,
                    assigned_at=now,
                    version=1,
                )
            )


def bootstrap_service(
    engine, *, production_activation_enabled: bool = False
) -> AccountAccessService:
    import hashlib

    return AccountAccessService(
        engine,
        security_pepper=PEPPER,
        bootstrap_enabled=True,
        production_activation_enabled=production_activation_enabled,
        bootstrap_secret_verifier=hashlib.sha256(BOOTSTRAP_SECRET.encode()).digest(),
    )


def test_bootstrap_disabled_production_and_trusted_configuration(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine)
    seed_security_roles(postgres_engine)
    with pytest.raises(PermissionError, match="disabled"):
        AccountAccessService(postgres_engine).bootstrap_first_administrator(
            target_account_id=account,
            presented_secret=BOOTSTRAP_SECRET,
            reason="initial_security_bootstrap",
            idempotency_key="bootstrap-disabled-1",
            trace=trace(),
        )
    with pytest.raises(PermissionError, match="production"):
        bootstrap_service(
            postgres_engine, production_activation_enabled=True
        ).bootstrap_first_administrator(
            target_account_id=account,
            presented_secret=BOOTSTRAP_SECRET,
            reason="initial_security_bootstrap",
            idempotency_key="bootstrap-production-1",
            trace=trace(),
        )
    with pytest.raises(PermissionError, match="denied"):
        bootstrap_service(postgres_engine).bootstrap_first_administrator(
            target_account_id=account,
            presented_secret="wrong-secret",
            reason="initial_security_bootstrap",
            idempotency_key="bootstrap-wrong-0001",
            trace=trace(),
        )


def test_bootstrap_is_one_time_atomic_secret_free_and_replay_safe(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine)
    seed_security_roles(postgres_engine)
    service = bootstrap_service(postgres_engine)
    assignment = service.bootstrap_first_administrator(
        target_account_id=account,
        presented_secret=BOOTSTRAP_SECRET,
        reason="initial_security_bootstrap",
        idempotency_key="bootstrap-success-1",
        trace=trace(),
    )
    with pytest.raises(PermissionError, match="already"):
        service.bootstrap_first_administrator(
            target_account_id=account,
            presented_secret=BOOTSTRAP_SECRET,
            reason="initial_security_bootstrap",
            idempotency_key="bootstrap-success-1",
            trace=trace(),
        )
    with postgres_engine.connect() as connection:
        row = connection.execute(select(identity_security_bootstrap)).mappings().one()
        assert row["assignment_id"] == assignment.assignment_id
        assert BOOTSTRAP_SECRET not in repr(dict(row))
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_outbox)
            ).scalar_one()
            == 1
        )


def test_concurrent_bootstrap_establishes_exactly_one_administrator(
    postgres_engine,
) -> None:
    first, second = seed_account(postgres_engine), seed_account(postgres_engine)
    seed_security_roles(postgres_engine)
    service = bootstrap_service(postgres_engine)

    def attempt(target):
        try:
            return service.bootstrap_first_administrator(
                target_account_id=target,
                presented_secret=BOOTSTRAP_SECRET,
                reason="concurrent_bootstrap",
                idempotency_key=f"bootstrap-{target}",
                trace=trace(),
            ).account_id
        except (PermissionError, AccountAccessConflict):
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (first, second)))
    assert sum(result is not None for result in results) == 1
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(identity_security_bootstrap)
            ).scalar_one()
            == 1
        )


def test_recovery_is_hashed_superseded_single_use_and_revokes_sessions(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    service.set_password(
        account_id=account,
        password="old password material value",
        idempotency_key="recovery-old-password",
        trace=trace(),
    )
    signed_in = service.authenticate(
        account_id=account,
        password="old password material value",
        client_reference=None,
        idempotency_key="recovery-session-1",
        trace=trace(),
    )
    first = service.initiate_recovery(
        account_id=account, idempotency_key="recovery-issue-0001", trace=trace()
    )
    second = service.initiate_recovery(
        account_id=account, idempotency_key="recovery-issue-0002", trace=trace()
    )
    assert first.accepted and second.accepted and first.token and second.token
    with postgres_engine.connect() as connection:
        rows = (
            connection.execute(
                select(account_recovery_tokens).order_by(
                    account_recovery_tokens.c.token_version
                )
            )
            .mappings()
            .all()
        )
    assert rows[0]["state"] == "superseded"
    assert rows[0]["token_hash"] != first.token.encode()
    assert first.token not in repr(rows)
    assert (
        service.complete_password_recovery(
            account_id=account,
            token=first.token,
            new_password="new password material value",
            idempotency_key="recovery-complete-old",
            trace=trace(),
        )
        is None
    )
    credential = service.complete_password_recovery(
        account_id=account,
        token=second.token,
        new_password="new password material value",
        idempotency_key="recovery-complete-new",
        trace=trace(),
    )
    assert credential is not None
    assert (
        signed_in.session_id is not None
        and service.validate_session(signed_in.session_id) is None
    )
    assert (
        service.complete_password_recovery(
            account_id=account,
            token=second.token,
            new_password="new password material value",
            idempotency_key="recovery-complete-replay",
            trace=trace(),
        )
        is None
    )
    assert service.authenticate(
        account_id=account,
        password="new password material value",
        client_reference=None,
        idempotency_key="recovery-new-login",
        trace=trace(),
    ).authenticated


def test_recovery_concurrent_consumption_allows_one_password_replacement(
    postgres_engine,
) -> None:
    account = seed_account(postgres_engine)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    service.set_password(
        account_id=account,
        password="old concurrent password",
        idempotency_key="concurrent-old-password",
        trace=trace(),
    )
    issued = service.initiate_recovery(
        account_id=account, idempotency_key="concurrent-recovery-issue", trace=trace()
    )
    assert issued.token

    def consume(index):
        return service.complete_password_recovery(
            account_id=account,
            token=issued.token,
            new_password="new concurrent password",
            idempotency_key=f"concurrent-recovery-{index}",
            trace=trace(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, (1, 2)))
    assert sum(result is not None for result in results) == 1
    with postgres_engine.connect() as connection:
        row = connection.execute(select(account_recovery_tokens)).mappings().one()
    assert row["state"] == "consumed"


def test_recovery_survives_controlled_connection_pool_restart(postgres_engine) -> None:
    account = seed_account(postgres_engine)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    service.set_password(
        account_id=account,
        password="restart old password",
        idempotency_key="restart-old-password",
        trace=trace(),
    )
    issued = service.initiate_recovery(
        account_id=account, idempotency_key="restart-recovery-issue", trace=trace()
    )
    assert issued.token
    postgres_engine.dispose()
    restarted = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    assert (
        restarted.complete_password_recovery(
            account_id=account,
            token=issued.token,
            new_password="restart new password",
            idempotency_key="restart-recovery-complete",
            trace=trace(),
        )
        is not None
    )


def test_recovery_expiry_wrong_account_revocation_and_enumeration_shape(
    postgres_engine,
) -> None:
    admin, account, other = (
        seed_account(postgres_engine),
        seed_account(postgres_engine),
        seed_account(postgres_engine),
    )
    seed_security_roles(postgres_engine, admin)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    issued = service.initiate_recovery(
        account_id=account,
        idempotency_key="recovery-expiry-1",
        trace=trace(),
        lifetime=timedelta(minutes=5),
        at=datetime.now(UTC),
    )
    missing = service.initiate_recovery(
        account_id=uuid4(), idempotency_key="recovery-missing-1", trace=trace()
    )
    assert issued.accepted == missing.accepted
    assert issued.token and issued.token_id
    assert (
        service.complete_password_recovery(
            account_id=other,
            token=issued.token,
            new_password="replacement password value",
            idempotency_key="recovery-wrong-account",
            trace=trace(),
        )
        is None
    )
    revoked = service.revoke_recovery_token(
        actor_account_id=admin,
        token_id=issued.token_id,
        reason="administrator_revocation",
        idempotency_key="recovery-revoke-1",
        trace=trace(),
    )
    assert revoked.state == "revoked"
    assert (
        service.complete_password_recovery(
            account_id=account,
            token=issued.token,
            new_password="replacement password value",
            idempotency_key="recovery-revoked-use",
            trace=trace(),
        )
        is None
    )
    expired = service.initiate_recovery(
        account_id=account,
        idempotency_key="recovery-expired-issue",
        trace=trace(),
        lifetime=timedelta(minutes=5),
        at=datetime.now(UTC) - timedelta(minutes=6),
    )
    assert (
        expired.token
        and service.complete_password_recovery(
            account_id=account,
            token=expired.token,
            new_password="replacement password value",
            idempotency_key="recovery-expired-use",
            trace=trace(),
        )
        is None
    )


def test_forced_change_denies_permissions_revokes_sessions_and_clears(
    postgres_engine,
) -> None:
    admin, account = seed_account(postgres_engine), seed_account(postgres_engine)
    seed_security_roles(postgres_engine, admin)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)
    service.set_password(
        account_id=account,
        password="current password material",
        idempotency_key="forced-password-1",
        trace=trace(),
    )
    session = service.authenticate(
        account_id=account,
        password="current password material",
        client_reference=None,
        idempotency_key="forced-session-1",
        trace=trace(),
    )
    required = service.require_credential_change(
        actor_account_id=admin,
        account_id=account,
        expected_version=1,
        reason="credential_compromise",
        provenance="administrator_action",
        idempotency_key="forced-require-1",
        trace=trace(),
    )
    assert required.credential_change_required
    assert service.effective_permissions(account, {"anything.allowed"}) == frozenset()
    assert session.session_id and service.validate_session(session.session_id) is None
    changed = service.complete_forced_credential_change(
        account_id=account,
        current_password="current password material",
        new_password="replacement password material",
        idempotency_key="forced-complete-1",
        trace=trace(),
    )
    assert changed.credential_version == 2
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
    assert not row["credential_change_required"]


def test_origin_limit_is_bounded_peppered_and_window_resets(postgres_engine) -> None:
    service = AccountAccessService(
        postgres_engine,
        security_pepper=PEPPER,
        origin_attempt_limit=5,
        origin_attempt_window=timedelta(minutes=5),
    )
    now = datetime.now(UTC)
    for index in range(6):
        result = service.authenticate(
            account_id=uuid4(),
            password="invalid password value",
            client_reference=None,
            client_origin="coarse-test-origin",
            idempotency_key=f"origin-attempt-{index}",
            trace=trace(),
            at=now,
        )
        assert not result.authenticated
    with postgres_engine.connect() as connection:
        row = connection.execute(select(authentication_origin_windows)).mappings().one()
    assert row["attempt_count"] == 6 and row["throttled_at"] is not None
    assert b"coarse-test-origin" not in row["origin_hash"]
    service.authenticate(
        account_id=uuid4(),
        password="invalid password value",
        client_reference=None,
        client_origin="coarse-test-origin",
        idempotency_key="origin-after-window",
        trace=trace(),
        at=now + timedelta(minutes=6),
    )
    with postgres_engine.connect() as connection:
        reset = (
            connection.execute(select(authentication_origin_windows)).mappings().one()
        )
    assert reset["attempt_count"] == 1 and reset["throttled_at"] is None


def test_recovery_event_failure_rolls_back_token(postgres_engine, monkeypatch) -> None:
    account = seed_account(postgres_engine)
    service = AccountAccessService(postgres_engine, security_pepper=PEPPER)

    def fail(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("injected recovery event failure")

    monkeypatch.setattr(PostgresDomainEventRepository, "append", fail)
    with pytest.raises(RuntimeError, match="injected recovery"):
        service.initiate_recovery(
            account_id=account, idempotency_key="recovery-rollback-1", trace=trace()
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(account_recovery_tokens)
            ).scalar_one()
            == 0
        )
