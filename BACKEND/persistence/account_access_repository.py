from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.identity.access_models import (
    AccountRoleAssignment,
    AccountSession,
    PasswordCredential,
    RecoveryTokenRecord,
)
from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.persistence.errors import OptimisticConcurrencyError, PersistenceError
from BACKEND.persistence.tables import (
    account_password_credentials,
    account_recovery_tokens,
    account_role_assignments,
    account_sessions,
    authentication_origin_windows,
    identity_accounts,
    identity_security_bootstrap,
    permissions,
    role_permissions,
    roles,
)


class AccountAccessConflict(PersistenceError):
    pass


def _credential(row: Mapping[Any, Any]) -> PasswordCredential:
    return PasswordCredential.model_validate(dict(row))


def _session(row: Mapping[Any, Any]) -> AccountSession:
    return AccountSession.model_validate(dict(row))


def _account(row: Mapping[Any, Any]) -> IdentityAccount:
    return IdentityAccount.model_validate(dict(row))


class PostgresAccountAccessRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_account(
        self, account_id: UUID, *, lock: bool = False
    ) -> IdentityAccount | None:
        statement = select(identity_accounts).where(
            identity_accounts.c.account_id == account_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _account(row)

    def active_credential(self, account_id: UUID) -> PasswordCredential | None:
        row = (
            self._connection.execute(
                select(account_password_credentials).where(
                    account_password_credentials.c.account_id == account_id,
                    account_password_credentials.c.superseded_at.is_(None),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _credential(row)

    def replace_credential(
        self, credential: PasswordCredential, *, at: datetime
    ) -> PasswordCredential:
        current = self.active_credential(credential.account_id)
        if current is not None:
            self._connection.execute(
                update(account_password_credentials)
                .where(
                    account_password_credentials.c.credential_id
                    == current.credential_id,
                    account_password_credentials.c.superseded_at.is_(None),
                )
                .values(superseded_at=at)
            )
        try:
            self._connection.execute(
                insert(account_password_credentials).values(
                    **credential.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise AccountAccessConflict("Credential version already exists") from error
        return credential

    def record_failed_attempt(
        self,
        account: IdentityAccount,
        *,
        at: datetime,
        threshold: int,
        window: timedelta = timedelta(minutes=15),
    ) -> IdentityAccount:
        reset = (
            account.failed_window_started_at is None
            or at >= account.failed_window_started_at + window
        )
        count = 1 if reset else account.failed_attempt_count + 1
        window_started = at if reset else account.failed_window_started_at
        state = (
            AccountLifecycle.LOCKED.value
            if count >= threshold and account.state is AccountLifecycle.ACTIVE
            else account.state.value
        )
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == account.version,
                )
                .values(
                    failed_attempt_count=count,
                    last_failed_at=at,
                    failed_window_started_at=window_started,
                    state=state,
                    updated_at=at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Account changed during authentication")
        return _account(row)

    def reset_failed_attempts(
        self, account: IdentityAccount, *, at: datetime
    ) -> IdentityAccount:
        if account.failed_attempt_count == 0:
            return account
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == account.version,
                )
                .values(
                    failed_attempt_count=0,
                    last_failed_at=None,
                    failed_window_started_at=None,
                    updated_at=at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one()
        )
        return _account(row)

    def transition(
        self, account: IdentityAccount, *, target: AccountLifecycle, at: datetime
    ) -> IdentityAccount:
        account.transition(target, at=at)
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == account.version,
                )
                .values(
                    state=target.value,
                    failed_attempt_count=0,
                    last_failed_at=None,
                    failed_window_started_at=None,
                    updated_at=at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Account changed")
        return _account(row)

    def create_session(self, session: AccountSession) -> AccountSession:
        try:
            self._connection.execute(
                insert(account_sessions).values(**session.model_dump(mode="python"))
            )
        except IntegrityError as error:
            raise AccountAccessConflict("Session already exists") from error
        return session

    def get_session(
        self, session_id: UUID, *, lock: bool = False
    ) -> AccountSession | None:
        statement = select(account_sessions).where(
            account_sessions.c.session_id == session_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _session(row)

    def touch_session(self, session: AccountSession, *, at: datetime) -> AccountSession:
        row = (
            self._connection.execute(
                update(account_sessions)
                .where(
                    account_sessions.c.session_id == session.session_id,
                    account_sessions.c.version == session.version,
                    account_sessions.c.revoked_at.is_(None),
                )
                .values(last_used_at=at, version=account_sessions.c.version + 1)
                .returning(account_sessions)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Session changed")
        return _session(row)

    def revoke_session(
        self, session: AccountSession, *, at: datetime, reason: str
    ) -> AccountSession:
        if session.revoked_at is not None:
            return session
        row = (
            self._connection.execute(
                update(account_sessions)
                .where(
                    account_sessions.c.session_id == session.session_id,
                    account_sessions.c.version == session.version,
                    account_sessions.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=at,
                    revocation_reason=reason,
                    version=account_sessions.c.version + 1,
                )
                .returning(account_sessions)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Session changed")
        return _session(row)

    def revoke_all_sessions(
        self, account_id: UUID, *, at: datetime, reason: str
    ) -> list[UUID]:
        rows = (
            self._connection.execute(
                update(account_sessions)
                .where(
                    account_sessions.c.account_id == account_id,
                    account_sessions.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=at,
                    revocation_reason=reason,
                    version=account_sessions.c.version + 1,
                )
                .returning(account_sessions.c.session_id)
            )
            .scalars()
            .all()
        )
        return list(rows)

    def has_permission(self, account_id: UUID, code: str, *, at: datetime) -> bool:
        del at
        return (
            self._connection.execute(
                select(permissions.c.permission_id)
                .select_from(
                    account_role_assignments.join(roles)
                    .join(role_permissions)
                    .join(permissions)
                )
                .where(
                    account_role_assignments.c.account_id == account_id,
                    account_role_assignments.c.revoked_at.is_(None),
                    permissions.c.code == code,
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def role_id(self, code: str) -> UUID | None:
        return self._connection.execute(
            select(roles.c.role_id).where(roles.c.code == code)
        ).scalar_one_or_none()

    def assign_role(self, assignment: AccountRoleAssignment) -> AccountRoleAssignment:
        try:
            self._connection.execute(
                insert(account_role_assignments).values(
                    **assignment.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise AccountAccessConflict(
                "Active role assignment already exists"
            ) from error
        return assignment

    def active_assignment(
        self, account_id: UUID, role_id: UUID
    ) -> AccountRoleAssignment | None:
        row = (
            self._connection.execute(
                select(account_role_assignments).where(
                    account_role_assignments.c.account_id == account_id,
                    account_role_assignments.c.role_id == role_id,
                    account_role_assignments.c.revoked_at.is_(None),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else AccountRoleAssignment.model_validate(dict(row))

    def get_assignment(self, assignment_id: UUID) -> AccountRoleAssignment | None:
        row = (
            self._connection.execute(
                select(account_role_assignments).where(
                    account_role_assignments.c.assignment_id == assignment_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else AccountRoleAssignment.model_validate(dict(row))

    def revoke_assignment(
        self,
        assignment: AccountRoleAssignment,
        *,
        actor_id: UUID,
        at: datetime,
        reason: str,
    ) -> AccountRoleAssignment:
        row = (
            self._connection.execute(
                update(account_role_assignments)
                .where(
                    account_role_assignments.c.assignment_id
                    == assignment.assignment_id,
                    account_role_assignments.c.version == assignment.version,
                    account_role_assignments.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=at,
                    revoked_by_account_id=actor_id,
                    revocation_reason=reason,
                    version=account_role_assignments.c.version + 1,
                )
                .returning(account_role_assignments)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Role assignment changed")
        return AccountRoleAssignment.model_validate(dict(row))

    def administrator_count(self) -> int:
        return int(
            self._connection.execute(
                select(func.count())
                .select_from(account_role_assignments.join(roles))
                .where(
                    roles.c.code == "platform_administrator",
                    account_role_assignments.c.revoked_at.is_(None),
                )
            ).scalar_one()
        )

    def complete_first_bootstrap(
        self,
        *,
        target_account_id: UUID,
        assignment_id: UUID,
        reason: str,
        command_id: UUID,
        correlation_id: UUID,
        at: datetime,
    ) -> None:
        try:
            self._connection.execute(
                insert(identity_security_bootstrap).values(
                    bootstrap_key="first_platform_administrator",
                    target_account_id=target_account_id,
                    assignment_id=assignment_id,
                    completed_at=at,
                    reason=reason,
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
            )
        except IntegrityError as error:
            raise AccountAccessConflict(
                "Platform bootstrap is already complete"
            ) from error

    def create_recovery_token(
        self, record: RecoveryTokenRecord, *, supersede_at: datetime
    ) -> RecoveryTokenRecord:
        self._connection.execute(
            update(account_recovery_tokens)
            .where(
                account_recovery_tokens.c.account_id == record.account_id,
                account_recovery_tokens.c.purpose == record.purpose,
                account_recovery_tokens.c.state == "active",
            )
            .values(
                state="superseded",
                superseded_at=supersede_at,
                version=account_recovery_tokens.c.version + 1,
            )
        )
        try:
            self._connection.execute(
                insert(account_recovery_tokens).values(
                    **record.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise AccountAccessConflict("Recovery token conflicts") from error
        return record

    def next_recovery_version(self, account_id: UUID, purpose: str) -> int:
        current = self._connection.execute(
            select(func.max(account_recovery_tokens.c.token_version)).where(
                account_recovery_tokens.c.account_id == account_id,
                account_recovery_tokens.c.purpose == purpose,
            )
        ).scalar_one()
        return 1 if current is None else int(current) + 1

    def recovery_by_hash(
        self, token_hash: bytes, *, lock: bool = False
    ) -> RecoveryTokenRecord | None:
        statement = select(account_recovery_tokens).where(
            account_recovery_tokens.c.token_hash == token_hash
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else RecoveryTokenRecord.model_validate(dict(row))

    def recovery_by_id(
        self, token_id: UUID, *, lock: bool = False
    ) -> RecoveryTokenRecord | None:
        statement = select(account_recovery_tokens).where(
            account_recovery_tokens.c.token_id == token_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else RecoveryTokenRecord.model_validate(dict(row))

    def transition_recovery(
        self, record: RecoveryTokenRecord, *, state: str, at: datetime
    ) -> RecoveryTokenRecord:
        timestamp_column = {
            "consumed": "consumed_at",
            "revoked": "revoked_at",
            "superseded": "superseded_at",
        }[state]
        row = (
            self._connection.execute(
                update(account_recovery_tokens)
                .where(
                    account_recovery_tokens.c.token_id == record.token_id,
                    account_recovery_tokens.c.version == record.version,
                    account_recovery_tokens.c.state == "active",
                )
                .values(
                    state=state,
                    **{timestamp_column: at},
                    version=account_recovery_tokens.c.version + 1,
                )
                .returning(account_recovery_tokens)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Recovery token changed")
        return RecoveryTokenRecord.model_validate(dict(row))

    def set_credential_change_required(
        self,
        account: IdentityAccount,
        *,
        required: bool,
        reason: str | None,
        provenance: str | None,
        at: datetime,
    ) -> IdentityAccount:
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == account.version,
                )
                .values(
                    credential_change_required=required,
                    credential_change_reason=reason if required else None,
                    credential_change_provenance=provenance if required else None,
                    updated_at=at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Account security state changed")
        return _account(row)

    def clear_recovery_security_state(
        self, account: IdentityAccount, *, at: datetime
    ) -> IdentityAccount:
        resulting_state = (
            AccountLifecycle.ACTIVE.value
            if account.state is AccountLifecycle.LOCKED
            else account.state.value
        )
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == account.version,
                )
                .values(
                    state=resulting_state,
                    failed_attempt_count=0,
                    last_failed_at=None,
                    failed_window_started_at=None,
                    credential_change_required=False,
                    credential_change_reason=None,
                    credential_change_provenance=None,
                    updated_at=at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Account security state changed")
        return _account(row)

    def consume_origin_attempt(
        self,
        origin_hash: bytes,
        *,
        at: datetime,
        window: timedelta,
        limit: int,
    ) -> bool:
        row = (
            self._connection.execute(
                select(authentication_origin_windows)
                .where(authentication_origin_windows.c.origin_hash == origin_hash)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            try:
                self._connection.execute(
                    insert(authentication_origin_windows).values(
                        origin_hash=origin_hash,
                        window_started_at=at,
                        attempt_count=1,
                        version=1,
                    )
                )
                return True
            except IntegrityError as error:
                raise OptimisticConcurrencyError("Origin window changed") from error
        expired = at >= row["window_started_at"] + window
        count = 1 if expired else int(row["attempt_count"]) + 1
        allowed = count <= limit
        self._connection.execute(
            update(authentication_origin_windows)
            .where(
                authentication_origin_windows.c.origin_hash == origin_hash,
                authentication_origin_windows.c.version == row["version"],
            )
            .values(
                window_started_at=at if expired else row["window_started_at"],
                attempt_count=count,
                throttled_at=None if expired or allowed else at,
                version=authentication_origin_windows.c.version + 1,
            )
        )
        return allowed
