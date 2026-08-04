import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.access_models import (
    AccountRoleAssignment,
    AccountSession,
    AuthenticationResult,
    OwnershipDecision,
    OwnershipRelationship,
    OwnershipResolver,
    PasswordCredential,
    RecoveryInitiationResult,
    RecoveryTokenRecord,
)
from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.identity.passwords import Argon2idPasswordVerifier
from BACKEND.persistence.account_access_repository import (
    PostgresAccountAccessRepository,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.kernel_models import (
    DomainEvent,
    IdempotencyRecord,
    canonical_request_hash,
)
from BACKEND.persistence.kernel_repository import (
    PostgresDomainEventRepository,
    PostgresIdempotencyRepository,
    PostgresTransactionalOutboxRepository,
)
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork

PLATFORM_ROLES = frozenset(
    {"authenticated_user", "platform_support", "platform_administrator"}
)


class AccountAccessUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "AccountAccessUnitOfWork":
        super().__enter__()
        return self

    @property
    def access(self) -> PostgresAccountAccessRepository:
        return self.repository("access", PostgresAccountAccessRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)


class AccountAccessService:
    """PRE-PRODUCTION account-native credential, session and RBAC boundary."""

    def __init__(
        self,
        engine: Engine,
        *,
        failed_attempt_limit: int = 5,
        failed_attempt_window: timedelta = timedelta(minutes=15),
        origin_attempt_limit: int = 20,
        origin_attempt_window: timedelta = timedelta(minutes=5),
        absolute_lifetime: timedelta = timedelta(days=7),
        inactivity_timeout: timedelta = timedelta(hours=12),
        security_pepper: bytes | None = None,
        bootstrap_enabled: bool = False,
        production_activation_enabled: bool = False,
        bootstrap_secret_verifier: bytes | None = None,
    ) -> None:
        if not 2 <= failed_attempt_limit <= 20:
            raise ValueError("Failed-attempt limit must be between 2 and 20")
        if not 5 <= origin_attempt_limit <= 100:
            raise ValueError("Origin attempt limit must be between 5 and 100")
        if security_pepper is not None and len(security_pepper) < 32:
            raise ValueError("Security pepper must be at least 32 bytes")
        if (
            bootstrap_secret_verifier is not None
            and len(bootstrap_secret_verifier) != 32
        ):
            raise ValueError("Bootstrap secret verifier must be 32 bytes")
        if (
            not timedelta(minutes=5)
            <= inactivity_timeout
            < absolute_lifetime
            <= timedelta(days=30)
        ):
            raise ValueError("Session lifetimes are outside approved bounds")
        self._engine = engine
        self._failed_attempt_limit = failed_attempt_limit
        self._failed_attempt_window = failed_attempt_window
        self._origin_attempt_limit = origin_attempt_limit
        self._origin_attempt_window = origin_attempt_window
        self._absolute_lifetime = absolute_lifetime
        self._inactivity_timeout = inactivity_timeout
        self._passwords = Argon2idPasswordVerifier()
        self._dummy_verifier = self._passwords.hash(secrets.token_urlsafe(32))
        self._security_pepper = security_pepper
        self._bootstrap_enabled = bootstrap_enabled
        self._production_activation_enabled = production_activation_enabled
        self._bootstrap_secret_verifier = bootstrap_secret_verifier
        self._factories = {
            "access": PostgresAccountAccessRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _uow(self) -> AccountAccessUnitOfWork:
        return AccountAccessUnitOfWork(self._engine, self._factories)

    def set_password(
        self,
        *,
        account_id: UUID,
        password: str,
        idempotency_key: str,
        trace: TraceContext,
        actor_account_id: UUID | None = None,
        at: datetime | None = None,
    ) -> PasswordCredential:
        self._validate_password(password)
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.password.set",
                str(actor_account_id or account_id),
                idempotency_key,
                f"{account_id}:password-replacement",
                trace,
                instant,
            )
            existing = unit.access.active_credential(account_id)
            if reservation.completed_at is not None and existing is not None:
                return existing
            account = unit.access.get_account(account_id, lock=True)
            if account is None or account.state is AccountLifecycle.CLOSED:
                raise ValueError("Account is unavailable")
            credential = PasswordCredential(
                account_id=account_id,
                credential_version=1
                if existing is None
                else existing.credential_version + 1,
                scheme=self._passwords.scheme,
                verifier=self._passwords.hash(password),
                created_at=instant,
            )
            unit.access.replace_credential(credential, at=instant)
            self._record(
                unit,
                trace,
                event_type="identity.credential_changed",
                aggregate_id=account_id,
                action="identity.credential.changed",
                actor_id=actor_account_id,
                payload={"credential_version": credential.credential_version},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"credential/{credential.credential_id}",
                completed_at=instant,
            )
            return credential

    def authenticate(
        self,
        *,
        account_id: UUID,
        password: str,
        client_reference: str | None,
        idempotency_key: str,
        trace: TraceContext,
        client_origin: str | None = None,
        at: datetime | None = None,
    ) -> AuthenticationResult:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.authenticate",
                str(account_id),
                idempotency_key,
                str(account_id),
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                ref = reservation.response_reference or "denied"
                return AuthenticationResult(
                    authenticated=ref.startswith("session/"),
                    session_id=UUID(ref.split("/", 1)[1])
                    if ref.startswith("session/")
                    else None,
                    reason=(
                        "authenticated"
                        if ref.startswith("session/")
                        else "authentication_failed"
                    ),
                )
            if client_origin is not None and not unit.access.consume_origin_attempt(
                self._security_hash(client_origin),
                at=instant,
                window=self._origin_attempt_window,
                limit=self._origin_attempt_limit,
            ):
                self._audit(
                    unit,
                    trace,
                    action="identity.authentication.throttled",
                    actor_id=None,
                    resource_id="coarse_origin",
                    outcome=AuditOutcome.DENIED,
                    reason="bounded_origin_limit",
                    key=f"throttle-{idempotency_key}",
                    at=instant,
                )
                unit.idempotency.complete(
                    record=reservation,
                    response_reference="denied",
                    completed_at=instant,
                )
                return AuthenticationResult(authenticated=False)
            account = unit.access.get_account(account_id, lock=True)
            credential = (
                unit.access.active_credential(account_id)
                if account is not None
                else None
            )
            verifier = (
                credential.verifier if credential is not None else self._dummy_verifier
            )
            valid = self._passwords.verify(verifier, password)
            if (
                account is None
                or credential is None
                or not valid
                or account.state is not AccountLifecycle.ACTIVE
            ):
                if account is not None and account.state is AccountLifecycle.ACTIVE:
                    updated = unit.access.record_failed_attempt(
                        account,
                        at=instant,
                        threshold=self._failed_attempt_limit,
                        window=self._failed_attempt_window,
                    )
                    if updated.state is AccountLifecycle.LOCKED:
                        self._record(
                            unit,
                            trace,
                            event_type="identity.account_locked",
                            aggregate_id=account_id,
                            action="identity.account.locked",
                            actor_id=None,
                            payload={"reason": "failed_attempt_limit"},
                            key=f"lock-{idempotency_key}",
                            at=instant,
                        )
                self._audit(
                    unit,
                    trace,
                    action="identity.authentication.denied",
                    actor_id=None,
                    resource_id=str(account_id),
                    outcome=AuditOutcome.DENIED,
                    reason="invalid_credentials_or_state",
                    key=f"deny-{idempotency_key}",
                    at=instant,
                )
                unit.idempotency.complete(
                    record=reservation,
                    response_reference="denied",
                    completed_at=instant,
                )
                return AuthenticationResult(authenticated=False)
            account = unit.access.reset_failed_attempts(account, at=instant)
            if self._passwords.needs_upgrade(credential.verifier):
                replacement = PasswordCredential(
                    account_id=account_id,
                    credential_version=credential.credential_version + 1,
                    scheme=self._passwords.scheme,
                    verifier=self._passwords.hash(password),
                    created_at=instant,
                )
                unit.access.replace_credential(replacement, at=instant)
                self._record(
                    unit,
                    trace,
                    event_type="identity.credential_changed",
                    aggregate_id=account_id,
                    action="identity.credential.upgraded",
                    actor_id=account_id,
                    payload={"credential_version": replacement.credential_version},
                    key=f"upgrade-{idempotency_key}",
                    at=instant,
                )
            session = AccountSession(
                account_id=account_id,
                client_reference=client_reference,
                created_at=instant,
                last_used_at=instant,
                absolute_expires_at=instant + self._absolute_lifetime,
                inactivity_seconds=int(self._inactivity_timeout.total_seconds()),
            )
            unit.access.create_session(session)
            self._record(
                unit,
                trace,
                event_type="identity.session_created",
                aggregate_id=session.session_id,
                action="identity.session.created",
                actor_id=account_id,
                payload={"account_id": str(account_id)},
                key=f"session-{idempotency_key}",
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"session/{session.session_id}",
                completed_at=instant,
            )
            return AuthenticationResult(
                authenticated=True,
                session_id=session.session_id,
                reason="authenticated",
            )

    def validate_session(
        self, session_id: UUID, *, at: datetime | None = None
    ) -> AccountSession | None:
        instant = self._at(at)
        with self._uow() as unit:
            session = unit.access.get_session(session_id, lock=True)
            if session is None or not session.active_at(instant):
                return None
            account = unit.access.get_account(session.account_id)
            if account is None or account.state is not AccountLifecycle.ACTIVE:
                return None
            return unit.access.touch_session(session, at=instant)

    def rotate_session(
        self,
        *,
        session_id: UUID,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AccountSession:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.session.rotate",
                str(session_id),
                idempotency_key,
                str(session_id),
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                replacement_id = UUID(
                    (reservation.response_reference or "session/").split("/", 1)[1]
                )
                replacement = unit.access.get_session(replacement_id)
                if replacement is None:
                    raise RuntimeError("Idempotent session replacement is missing")
                return replacement
            current = unit.access.get_session(session_id, lock=True)
            if current is None or not current.active_at(instant):
                raise PermissionError("Session is unavailable")
            unit.access.revoke_session(current, at=instant, reason="rotated")
            replacement = AccountSession(
                account_id=current.account_id,
                client_reference=current.client_reference,
                created_at=instant,
                last_used_at=instant,
                absolute_expires_at=instant + self._absolute_lifetime,
                inactivity_seconds=current.inactivity_seconds,
                rotated_from_session_id=current.session_id,
            )
            unit.access.create_session(replacement)
            self._record(
                unit,
                trace,
                event_type="identity.session_revoked",
                aggregate_id=current.session_id,
                action="identity.session.revoked",
                actor_id=current.account_id,
                payload={"reason": "rotated"},
                key=f"revoke-{idempotency_key}",
                at=instant,
            )
            self._record(
                unit,
                trace,
                event_type="identity.session_created",
                aggregate_id=replacement.session_id,
                action="identity.session.rotated",
                actor_id=current.account_id,
                payload={"account_id": str(current.account_id)},
                key=f"create-{idempotency_key}",
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"session/{replacement.session_id}",
                completed_at=instant,
            )
            return replacement

    def revoke_session(
        self,
        *,
        actor_account_id: UUID,
        session_id: UUID,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AccountSession:
        self._safe_reason(reason)
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.session.revoke",
                str(actor_account_id),
                idempotency_key,
                f"{session_id}:{reason}",
                trace,
                instant,
            )
            session = unit.access.get_session(session_id, lock=True)
            if session is None:
                raise ValueError("Session does not exist")
            if (
                actor_account_id != session.account_id
                and not unit.access.has_permission(
                    actor_account_id, "identity.session.revoke_any", at=instant
                )
            ):
                raise PermissionError("Authorization denied")
            revoked = unit.access.revoke_session(session, at=instant, reason=reason)
            if reservation.completed_at is None:
                self._record(
                    unit,
                    trace,
                    event_type="identity.session_revoked",
                    aggregate_id=session_id,
                    action="identity.session.revoked",
                    actor_id=actor_account_id,
                    payload={"reason": reason},
                    key=idempotency_key,
                    at=instant,
                )
                unit.idempotency.complete(
                    record=reservation,
                    response_reference=f"session/{session_id}",
                    completed_at=instant,
                )
            return revoked

    def revoke_all_sessions(
        self,
        *,
        actor_account_id: UUID,
        account_id: UUID,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> tuple[UUID, ...]:
        self._safe_reason(reason)
        instant = self._at(at)
        with self._uow() as unit:
            if actor_account_id != account_id and not unit.access.has_permission(
                actor_account_id, "identity.session.revoke_any", at=instant
            ):
                raise PermissionError("Authorization denied")
            reservation = self._reserve(
                unit,
                "identity.session.revoke_all",
                str(actor_account_id),
                idempotency_key,
                f"{account_id}:{reason}",
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                return tuple()
            revoked = tuple(
                unit.access.revoke_all_sessions(account_id, at=instant, reason=reason)
            )
            for index, session_id in enumerate(revoked):
                self._record(
                    unit,
                    trace,
                    event_type="identity.session_revoked",
                    aggregate_id=session_id,
                    action="identity.session.revoked",
                    actor_id=actor_account_id,
                    payload={"reason": reason},
                    key=f"{idempotency_key}-{index}",
                    at=instant,
                )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"account/{account_id}/sessions/{len(revoked)}",
                completed_at=instant,
            )
            return revoked

    def transition_account(
        self,
        *,
        actor_account_id: UUID,
        account_id: UUID,
        target: AccountLifecycle,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> IdentityAccount:
        permission = {
            AccountLifecycle.ACTIVE: "identity.account.unlock",
            AccountLifecycle.SUSPENDED: "identity.account.suspend",
            AccountLifecycle.CLOSED: "identity.account.close",
        }.get(target)
        if permission is None:
            permission = "identity.account.activate"
        instant = self._at(at)
        with self._uow() as unit:
            if not unit.access.has_permission(actor_account_id, permission, at=instant):
                raise PermissionError("Authorization denied")
            reservation = self._reserve(
                unit,
                "identity.account.transition",
                str(actor_account_id),
                idempotency_key,
                f"{account_id}:{target.value}:{expected_version}",
                trace,
                instant,
            )
            account = unit.access.get_account(account_id, lock=True)
            if account is None:
                raise ValueError("Account does not exist")
            if reservation.completed_at is not None:
                return account
            if account.version != expected_version:
                from BACKEND.persistence.errors import OptimisticConcurrencyError

                raise OptimisticConcurrencyError("Account changed")
            updated = unit.access.transition(account, target=target, at=instant)
            event = {
                AccountLifecycle.ACTIVE: "identity.account_unlocked"
                if account.state is AccountLifecycle.LOCKED
                else "identity.account_activated",
                AccountLifecycle.SUSPENDED: "identity.account_suspended",
                AccountLifecycle.CLOSED: "identity.account_closed",
            }[target]
            self._record(
                unit,
                trace,
                event_type=event,
                aggregate_id=account_id,
                action=event.replace("_", "."),
                actor_id=actor_account_id,
                payload={
                    "previous_state": account.state.value,
                    "resulting_state": target.value,
                    "reason": reason,
                },
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"account/{account_id}/version/{updated.version}",
                completed_at=instant,
            )
            return updated

    def assign_role(
        self,
        *,
        actor_account_id: UUID,
        account_id: UUID,
        role_code: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AccountRoleAssignment:
        if role_code not in PLATFORM_ROLES:
            raise ValueError("Role is outside the approved platform role set")
        if actor_account_id == account_id and role_code == "platform_administrator":
            raise PermissionError("Administrative self-escalation is prohibited")
        instant = self._at(at)
        with self._uow() as unit:
            if not unit.access.has_permission(
                actor_account_id, "identity.role.assign", at=instant
            ):
                raise PermissionError("Authorization denied")
            role_id = unit.access.role_id(role_code)
            if role_id is None:
                raise RuntimeError("Approved role is not provisioned")
            reservation = self._reserve(
                unit,
                "identity.role.assign",
                str(actor_account_id),
                idempotency_key,
                f"{account_id}:{role_code}",
                trace,
                instant,
            )
            existing = unit.access.active_assignment(account_id, role_id)
            if existing is not None:
                unit.idempotency.complete(
                    record=reservation,
                    response_reference=f"assignment/{existing.assignment_id}",
                    completed_at=instant,
                )
                return existing
            assignment = unit.access.assign_role(
                AccountRoleAssignment(
                    account_id=account_id,
                    role_id=role_id,
                    assigned_by_account_id=actor_account_id,
                    assigned_at=instant,
                )
            )
            self._record(
                unit,
                trace,
                event_type="identity.role_assigned",
                aggregate_id=account_id,
                action="identity.role.assigned",
                actor_id=actor_account_id,
                payload={"role": role_code},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"assignment/{assignment.assignment_id}",
                completed_at=instant,
            )
            return assignment

    def remove_role(
        self,
        *,
        actor_account_id: UUID,
        account_id: UUID,
        role_code: str,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AccountRoleAssignment:
        instant = self._at(at)
        with self._uow() as unit:
            if not unit.access.has_permission(
                actor_account_id, "identity.role.remove", at=instant
            ):
                raise PermissionError("Authorization denied")
            reservation = self._reserve(
                unit,
                "identity.role.remove",
                str(actor_account_id),
                idempotency_key,
                f"{account_id}:{role_code}:{reason}",
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                assignment_id = UUID(
                    (reservation.response_reference or "assignment/").split("/", 1)[1]
                )
                completed = unit.access.get_assignment(assignment_id)
                if completed is None:
                    raise RuntimeError("Idempotent role removal result is missing")
                return completed
            role_id = unit.access.role_id(role_code)
            assignment = (
                None
                if role_id is None
                else unit.access.active_assignment(account_id, role_id)
            )
            if assignment is None:
                raise ValueError("Active role assignment does not exist")
            revoked = unit.access.revoke_assignment(
                assignment, actor_id=actor_account_id, at=instant, reason=reason
            )
            self._record(
                unit,
                trace,
                event_type="identity.role_removed",
                aggregate_id=account_id,
                action="identity.role.removed",
                actor_id=actor_account_id,
                payload={"role": role_code, "reason": reason},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"assignment/{revoked.assignment_id}",
                completed_at=instant,
            )
            return revoked

    def bootstrap_first_administrator(
        self,
        *,
        target_account_id: UUID,
        presented_secret: str,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AccountRoleAssignment:
        self._safe_reason(reason)
        if not self._bootstrap_enabled:
            raise PermissionError("Administrator bootstrap is disabled")
        if self._production_activation_enabled:
            raise PermissionError("Administrator bootstrap is prohibited in production")
        if self._bootstrap_secret_verifier is None or trace.command_id is None:
            raise PermissionError("Trusted bootstrap configuration is incomplete")
        presented = hashlib.sha256(presented_secret.encode()).digest()
        if not hmac.compare_digest(presented, self._bootstrap_secret_verifier):
            raise PermissionError("Administrator bootstrap denied")
        instant = self._at(at)
        with self._uow() as unit:
            if unit.access.administrator_count() != 0:
                raise PermissionError("Platform administrator is already established")
            account = unit.access.get_account(target_account_id, lock=True)
            if account is None or account.state is not AccountLifecycle.ACTIVE:
                raise PermissionError("Bootstrap target Account is not eligible")
            role_id = unit.access.role_id("platform_administrator")
            if role_id is None:
                raise RuntimeError("Platform administrator role is not provisioned")
            reservation = self._reserve(
                unit,
                "identity.bootstrap.first_administrator",
                "trusted_bootstrap",
                idempotency_key,
                f"{target_account_id}:{reason}",
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                raise PermissionError("Administrator bootstrap replay rejected")
            assignment = unit.access.assign_role(
                AccountRoleAssignment(
                    account_id=target_account_id,
                    role_id=role_id,
                    assigned_by_account_id=target_account_id,
                    assigned_at=instant,
                )
            )
            unit.access.complete_first_bootstrap(
                target_account_id=target_account_id,
                assignment_id=assignment.assignment_id,
                reason=reason,
                command_id=trace.command_id,
                correlation_id=trace.correlation_id,
                at=instant,
            )
            self._record(
                unit,
                trace,
                event_type="identity.bootstrap_completed",
                aggregate_id=target_account_id,
                action="identity.bootstrap.completed",
                actor_id=None,
                payload={"assignment_id": str(assignment.assignment_id)},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"assignment/{assignment.assignment_id}",
                completed_at=instant,
            )
            return assignment

    def initiate_recovery(
        self,
        *,
        account_id: UUID,
        idempotency_key: str,
        trace: TraceContext,
        lifetime: timedelta = timedelta(minutes=20),
        at: datetime | None = None,
    ) -> RecoveryInitiationResult:
        if not timedelta(minutes=5) <= lifetime <= timedelta(hours=1):
            raise ValueError("Recovery lifetime is outside approved bounds")
        self._require_security_pepper()
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.recovery.initiate",
                "recovery_boundary",
                idempotency_key,
                str(account_id),
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                return RecoveryInitiationResult()
            account = unit.access.get_account(account_id, lock=True)
            if account is None or account.state is AccountLifecycle.CLOSED:
                unit.idempotency.complete(
                    record=reservation,
                    response_reference="recovery/accepted",
                    completed_at=instant,
                )
                return RecoveryInitiationResult()
            token = secrets.token_urlsafe(32)
            record = RecoveryTokenRecord(
                account_id=account_id,
                token_version=unit.access.next_recovery_version(
                    account_id, "password_recovery"
                ),
                token_hash=self._security_hash(token),
                created_at=instant,
                expires_at=instant + lifetime,
            )
            unit.access.create_recovery_token(record, supersede_at=instant)
            self._record(
                unit,
                trace,
                event_type="identity.recovery_issued",
                aggregate_id=account_id,
                action="identity.recovery.issued",
                actor_id=None,
                payload={"token_id": str(record.token_id), "purpose": record.purpose},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"recovery/{record.token_id}",
                completed_at=instant,
            )
            return RecoveryInitiationResult(
                token=token, token_id=record.token_id, expires_at=record.expires_at
            )

    def complete_password_recovery(
        self,
        *,
        account_id: UUID,
        token: str,
        new_password: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> PasswordCredential | None:
        self._validate_password(new_password)
        self._require_security_pepper()
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.recovery.complete",
                str(account_id),
                idempotency_key,
                f"{account_id}:password_recovery",
                trace,
                instant,
            )
            if reservation.completed_at is not None:
                return unit.access.active_credential(account_id)
            record = unit.access.recovery_by_hash(self._security_hash(token), lock=True)
            valid = (
                record is not None
                and record.account_id == account_id
                and record.purpose == "password_recovery"
                and record.state == "active"
                and instant < record.expires_at
            )
            if not valid or record is None:
                self._audit(
                    unit,
                    trace,
                    action="identity.recovery.rejected",
                    actor_id=None,
                    resource_id=str(account_id),
                    outcome=AuditOutcome.DENIED,
                    reason="invalid_expired_or_mismatched",
                    key=f"reject-{idempotency_key}",
                    at=instant,
                )
                unit.idempotency.complete(
                    record=reservation,
                    response_reference="recovery/rejected",
                    completed_at=instant,
                )
                return None
            account = unit.access.get_account(account_id, lock=True)
            if account is None or account.state in {
                AccountLifecycle.SUSPENDED,
                AccountLifecycle.CLOSED,
            }:
                return None
            current = unit.access.active_credential(account_id)
            credential = PasswordCredential(
                account_id=account_id,
                credential_version=1
                if current is None
                else current.credential_version + 1,
                scheme=self._passwords.scheme,
                verifier=self._passwords.hash(new_password),
                created_at=instant,
            )
            unit.access.replace_credential(credential, at=instant)
            unit.access.transition_recovery(record, state="consumed", at=instant)
            revoked = unit.access.revoke_all_sessions(
                account_id, at=instant, reason="password_recovery"
            )
            unit.access.clear_recovery_security_state(account, at=instant)
            self._record(
                unit,
                trace,
                event_type="identity.recovery_consumed",
                aggregate_id=account_id,
                action="identity.recovery.consumed",
                actor_id=None,
                payload={"token_id": str(record.token_id)},
                key=f"recovery-{idempotency_key}",
                at=instant,
            )
            self._record(
                unit,
                trace,
                event_type="identity.credential_changed",
                aggregate_id=account_id,
                action="identity.credential.recovered",
                actor_id=None,
                payload={"credential_version": credential.credential_version},
                key=f"credential-{idempotency_key}",
                at=instant,
            )
            self._record(
                unit,
                trace,
                event_type="identity.sessions_revoked",
                aggregate_id=account_id,
                action="identity.sessions.revoked",
                actor_id=None,
                payload={"count": len(revoked), "reason": "password_recovery"},
                key=f"sessions-{idempotency_key}",
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"credential/{credential.credential_id}",
                completed_at=instant,
            )
            return credential

    def revoke_recovery_token(
        self,
        *,
        actor_account_id: UUID,
        token_id: UUID,
        reason: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> RecoveryTokenRecord:
        self._safe_reason(reason)
        instant = self._at(at)
        with self._uow() as unit:
            if not unit.access.has_permission(
                actor_account_id, "identity.recovery.revoke", at=instant
            ):
                raise PermissionError("Authorization denied")
            reservation = self._reserve(
                unit,
                "identity.recovery.revoke",
                str(actor_account_id),
                idempotency_key,
                f"{token_id}:{reason}",
                trace,
                instant,
            )
            record = unit.access.recovery_by_id(token_id, lock=True)
            if record is None:
                raise ValueError("Recovery token does not exist")
            if reservation.completed_at is not None:
                return record
            revoked = unit.access.transition_recovery(
                record, state="revoked", at=instant
            )
            self._record(
                unit,
                trace,
                event_type="identity.recovery_revoked",
                aggregate_id=record.account_id,
                action="identity.recovery.revoked",
                actor_id=actor_account_id,
                payload={"token_id": str(token_id), "reason": reason},
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"recovery/{token_id}",
                completed_at=instant,
            )
            return revoked

    def require_credential_change(
        self,
        *,
        actor_account_id: UUID,
        account_id: UUID,
        expected_version: int,
        reason: str,
        provenance: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> IdentityAccount:
        self._safe_reason(reason)
        self._safe_reason(provenance)
        instant = self._at(at)
        with self._uow() as unit:
            if not unit.access.has_permission(
                actor_account_id, "identity.account.force_credential_change", at=instant
            ):
                raise PermissionError("Authorization denied")
            reservation = self._reserve(
                unit,
                "identity.credential.force_change",
                str(actor_account_id),
                idempotency_key,
                f"{account_id}:{expected_version}:{reason}:{provenance}",
                trace,
                instant,
            )
            account = unit.access.get_account(account_id, lock=True)
            if account is None:
                raise ValueError("Account does not exist")
            if reservation.completed_at is not None:
                return account
            if account.version != expected_version:
                from BACKEND.persistence.errors import OptimisticConcurrencyError

                raise OptimisticConcurrencyError("Account changed")
            updated = unit.access.set_credential_change_required(
                account, required=True, reason=reason, provenance=provenance, at=instant
            )
            revoked = unit.access.revoke_all_sessions(
                account_id, at=instant, reason="credential_change_required"
            )
            self._record(
                unit,
                trace,
                event_type="identity.credential_change_required",
                aggregate_id=account_id,
                action="identity.credential.change_required",
                actor_id=actor_account_id,
                payload={
                    "reason": reason,
                    "provenance": provenance,
                    "sessions_revoked": len(revoked),
                },
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"account/{account_id}/version/{updated.version}",
                completed_at=instant,
            )
            return updated

    def complete_forced_credential_change(
        self,
        *,
        account_id: UUID,
        current_password: str,
        new_password: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> PasswordCredential:
        self._validate_password(new_password)
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "identity.credential.complete_forced_change",
                str(account_id),
                idempotency_key,
                f"{account_id}:forced_change",
                trace,
                instant,
            )
            current = unit.access.active_credential(account_id)
            if reservation.completed_at is not None and current is not None:
                return current
            account = unit.access.get_account(account_id, lock=True)
            if (
                account is None
                or not account.credential_change_required
                or current is None
                or not self._passwords.verify(current.verifier, current_password)
            ):
                raise PermissionError("Credential change denied")
            replacement = PasswordCredential(
                account_id=account_id,
                credential_version=current.credential_version + 1,
                scheme=self._passwords.scheme,
                verifier=self._passwords.hash(new_password),
                created_at=instant,
            )
            unit.access.replace_credential(replacement, at=instant)
            unit.access.clear_recovery_security_state(account, at=instant)
            revoked = unit.access.revoke_all_sessions(
                account_id, at=instant, reason="credential_changed"
            )
            self._record(
                unit,
                trace,
                event_type="identity.credential_changed",
                aggregate_id=account_id,
                action="identity.credential.forced_change_completed",
                actor_id=account_id,
                payload={
                    "credential_version": replacement.credential_version,
                    "sessions_revoked": len(revoked),
                },
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"credential/{replacement.credential_id}",
                completed_at=instant,
            )
            return replacement

    def effective_permissions(
        self,
        account_id: UUID,
        permission_codes: set[str],
        *,
        at: datetime | None = None,
    ) -> frozenset[str]:
        instant = self._at(at)
        with self._uow() as unit:
            account = unit.access.get_account(account_id)
            if account is None or account.state is not AccountLifecycle.ACTIVE:
                return frozenset()
            if account.credential_change_required:
                return frozenset()
            return frozenset(
                code
                for code in permission_codes
                if unit.access.has_permission(account_id, code, at=instant)
            )

    def authorize_ownership(
        self,
        *,
        account_id: UUID,
        resource_type: str,
        resource_id: str,
        resolver: OwnershipResolver,
        allow_delegate: bool = True,
        request_administrative_override: bool = False,
        at: datetime | None = None,
    ) -> OwnershipDecision:
        relationship = resolver.relationship(
            account_id=account_id, resource_type=resource_type, resource_id=resource_id
        )
        if relationship is OwnershipRelationship.OWNER:
            return OwnershipDecision(allowed=True, reason="resource_owner")
        if allow_delegate and relationship is OwnershipRelationship.DELEGATE:
            return OwnershipDecision(allowed=True, reason="delegated_access")
        if request_administrative_override:
            with self._uow() as unit:
                if unit.access.has_permission(
                    account_id, "identity.ownership.override", at=self._at(at)
                ):
                    return OwnershipDecision(
                        allowed=True, reason="explicit_administrative_override"
                    )
        return OwnershipDecision(allowed=False, reason="ownership_not_established")

    def _reserve(
        self,
        unit: AccountAccessUnitOfWork,
        scope: str,
        actor: str,
        key: str,
        material: str,
        trace: TraceContext,
        at: datetime,
    ) -> IdempotencyRecord:
        if trace.command_id is None:
            raise ValueError("Mutation requires command identifier")
        return unit.idempotency.reserve(
            IdempotencyRecord(
                scope=scope,
                actor_reference=actor,
                idempotency_key=key,
                request_hash=canonical_request_hash(material.encode()),
                command_id=trace.command_id,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                created_at=at,
            )
        )

    def _record(
        self,
        unit: AccountAccessUnitOfWork,
        trace: TraceContext,
        *,
        event_type: str,
        aggregate_id: UUID,
        action: str,
        actor_id: UUID | None,
        payload: dict[str, str | int | bool | None],
        key: str,
        at: datetime,
    ) -> None:
        derived = hashlib.sha256(key.encode()).hexdigest()[:32]
        unit.events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type="identity_account",
                aggregate_id=str(aggregate_id),
                source_module="identity_access",
                schema_version=1,
                occurred_at=at,
                payload=payload,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                command_id=trace.command_id,
                causation_id=trace.causation_id,
                idempotency_key=f"event-{derived}",
            )
        )
        self._audit(
            unit,
            trace,
            action=action,
            actor_id=actor_id,
            resource_id=str(aggregate_id),
            outcome=AuditOutcome.SUCCESS,
            reason=None,
            key=f"audit-{derived}",
            at=at,
        )

    @staticmethod
    def _audit(
        unit: AccountAccessUnitOfWork,
        trace: TraceContext,
        *,
        action: str,
        actor_id: UUID | None,
        resource_id: str,
        outcome: AuditOutcome,
        reason: str | None,
        key: str,
        at: datetime,
    ) -> None:
        unit.audit.append(
            AuditEvent(
                occurred_at=at,
                actor_type=ActorType.SYSTEM if actor_id is None else ActorType.SERVICE,
                actor_id=None if actor_id is None else str(actor_id),
                action=action,
                resource_type="identity_account",
                resource_id=resource_id,
                outcome=outcome,
                reason=reason,
                correlation_id=trace.correlation_id,
                causation_id=trace.causation_id,
                request_id=trace.request_id,
                source_module="identity_access",
                safe_metadata={"category": "identity", "operation": action},
                idempotency_key=key,
            )
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must contain 12 to 128 characters")

    @staticmethod
    def _safe_reason(reason: str) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{1,62}", reason) is None:
            raise ValueError("Reason must be a safe category")

    def _require_security_pepper(self) -> bytes:
        if self._security_pepper is None:
            raise RuntimeError("Identity security pepper is not configured")
        return self._security_pepper

    def _security_hash(self, value: str) -> bytes:
        return hmac.new(
            self._require_security_pepper(), value.encode(), hashlib.sha256
        ).digest()

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return instant.astimezone(UTC)
