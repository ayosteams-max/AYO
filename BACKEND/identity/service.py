from datetime import datetime
from uuid import UUID

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.models import AccountStatus
from BACKEND.identity.tokens import RefreshRotationOutcome, RefreshRotationResult
from BACKEND.persistence.composition import AyoPostgresUnitOfWork


class AuthenticationSecurityService:
    """Transactional security state changes; it does not authenticate requests."""

    def verify_challenge(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        challenge_id: UUID,
        verifier: bytes,
        at: datetime,
        correlation_id: UUID,
        request_id: UUID | None = None,
    ) -> bool:
        matched = unit_of_work.authentication_challenges.verify(
            challenge_id, verifier=verifier, at=at
        )
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=ActorType.ANONYMOUS,
                action=(
                    "authentication.succeeded" if matched else "authentication.failed"
                ),
                resource_type="authentication_challenge",
                resource_id=str(challenge_id),
                outcome=AuditOutcome.SUCCESS if matched else AuditOutcome.FAILED,
                reason=None if matched else "invalid_or_expired_challenge",
                correlation_id=correlation_id,
                request_id=request_id,
                source_module="identity",
                safe_metadata={
                    "category": "authentication",
                    "operation": "challenge_verify",
                },
            )
        )
        return matched

    def rotate_refresh_token(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        family_id: UUID,
        presented_hash: bytes,
        replacement_hash: bytes,
        at: datetime,
        correlation_id: UUID,
        request_id: UUID | None = None,
    ) -> RefreshRotationResult:
        result = unit_of_work.refresh_tokens.rotate(
            family_id=family_id,
            presented_hash=presented_hash,
            replacement_hash=replacement_hash,
            at=at,
        )
        action = {
            RefreshRotationOutcome.ROTATED: "authentication.session.refreshed",
            RefreshRotationOutcome.REPLAY_DETECTED: (
                "authentication.refresh_token.replay_detected"
            ),
            RefreshRotationOutcome.DENIED: "authentication.session.refresh_denied",
        }[result.outcome]
        outcome = (
            AuditOutcome.SUCCESS
            if result.outcome is RefreshRotationOutcome.ROTATED
            else AuditOutcome.DENIED
        )
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=ActorType.SYSTEM,
                action=action,
                resource_type="session",
                resource_id=str(result.session_id),
                outcome=outcome,
                reason=(
                    "refresh_token_replay"
                    if result.outcome is RefreshRotationOutcome.REPLAY_DETECTED
                    else None
                ),
                correlation_id=correlation_id,
                request_id=request_id,
                source_module="identity",
                safe_metadata={
                    "category": "authentication",
                    "operation": "refresh",
                },
            )
        )
        return result

    def revoke_all_sessions(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        identity_id: UUID,
        at: datetime,
        reason: str,
        correlation_id: UUID,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: str | None = None,
    ) -> int:
        count = unit_of_work.sessions.revoke_all_for_identity(
            identity_id, revoked_at=at, reason=reason
        )
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=actor_type,
                actor_id=actor_id,
                action="authentication.sessions.all_revoked",
                resource_type="identity",
                resource_id=str(identity_id),
                outcome=AuditOutcome.SUCCESS,
                reason=reason,
                correlation_id=correlation_id,
                source_module="identity",
                safe_metadata={
                    "category": "authentication",
                    "operation": "logout_all",
                },
            )
        )
        return count

    def change_account_status(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        identity_id: UUID,
        target: AccountStatus,
        at: datetime,
        correlation_id: UUID,
    ) -> None:
        identity = unit_of_work.identities.get(identity_id)
        if identity is None:
            raise ValueError("Identity does not exist")
        updated = identity.transition(target, at=at)
        unit_of_work.identities.save(updated, expected_version=identity.version)
        if target in {
            AccountStatus.SUSPENDED,
            AccountStatus.LOCKED,
            AccountStatus.DISABLED,
            AccountStatus.RECOVERY_PENDING,
        }:
            unit_of_work.sessions.revoke_all_for_identity(
                identity_id, revoked_at=at, reason=f"account_{target.value}"
            )
        action = {
            AccountStatus.SUSPENDED: "authentication.account.suspended",
            AccountStatus.LOCKED: "authentication.account.locked",
            AccountStatus.RECOVERY_PENDING: "authentication.recovery.started",
        }.get(target, f"authentication.account.{target.value}")
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=ActorType.SYSTEM,
                action=action,
                resource_type="identity",
                resource_id=str(identity_id),
                outcome=AuditOutcome.SUCCESS,
                reason=f"account_{target.value}",
                correlation_id=correlation_id,
                source_module="identity",
                safe_metadata={
                    "category": "authentication",
                    "state_from": identity.status.value,
                    "state_to": target.value,
                },
            )
        )
