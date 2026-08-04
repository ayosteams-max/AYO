import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import NoResultFound

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.authentication import (
    AuthenticationChallenge,
    ChallengeProtector,
    ChallengePurpose,
)
from BACKEND.identity.models import (
    AccountStatus,
    AssuranceLevel,
    Identity,
    IdentityType,
)
from BACKEND.identity.passwords import Argon2idPasswordVerifier
from BACKEND.identity.runtime_models import (
    AuthenticationSessionResponse,
    ContactKind,
    IdentityActivationProgress,
    RegistrationRequest,
    SignInRequest,
    VerificationPreparationResponse,
    normalize_contact,
)
from BACKEND.identity.runtime_tokens import AsymmetricJwtIssuer
from BACKEND.identity.tokens import RefreshRotationOutcome
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.identity_repository import DuplicateAuthenticationIdentifier
from BACKEND.rate_limit.models import RateLimitPolicy
from BACKEND.session.models import SessionRecord


class AuthenticationDenied(ValueError):
    pass


class AuthenticationRateLimited(ValueError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("authentication_rate_limited")
        self.retry_after_seconds = retry_after_seconds


class RegistrationConflict(ValueError):
    pass


class VerificationDeliveryUnavailable(RuntimeError):
    pass


class VerificationDelivery(Protocol):
    def deliver(
        self,
        *,
        kind: ContactKind,
        destination: str,
        code: str,
        expires_at: datetime,
    ) -> None: ...


class AuthenticationRuntime:
    """Canonical password/session orchestration over the certified PostgreSQL state."""

    _REGISTER_POLICY = RateLimitPolicy(
        name="auth.register",
        capacity=5,
        refill_tokens=Decimal(1),
        refill_period_seconds=60,
    )
    _SIGN_IN_POLICY = RateLimitPolicy(
        name="auth.sign_in",
        capacity=8,
        refill_tokens=Decimal(1),
        refill_period_seconds=30,
    )
    _REFRESH_POLICY = RateLimitPolicy(
        name="auth.refresh",
        capacity=20,
        refill_tokens=Decimal(1),
        refill_period_seconds=6,
    )
    _RECOVERY_POLICY = RateLimitPolicy(
        name="auth.recovery_prepare",
        capacity=3,
        refill_tokens=Decimal(1),
        refill_period_seconds=300,
    )
    _VERIFICATION_POLICY = RateLimitPolicy(
        name="auth.verification",
        capacity=5,
        refill_tokens=Decimal(1),
        refill_period_seconds=60,
    )

    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        token_issuer: AsymmetricJwtIssuer,
        identifier_pepper: bytes,
        challenge_protector: ChallengeProtector | None = None,
        verification_delivery: VerificationDelivery | None = None,
        refresh_lifetime: timedelta = timedelta(days=30),
    ) -> None:
        if len(identifier_pepper) < 32:
            raise ValueError(
                "Authentication identifier pepper must be at least 32 bytes"
            )
        if not timedelta(days=1) <= refresh_lifetime <= timedelta(days=90):
            raise ValueError("Refresh-token lifetime must be between 1 and 90 days")
        self._composition = composition
        self._issuer = token_issuer
        self._pepper = identifier_pepper
        self._refresh_lifetime = refresh_lifetime
        self._challenge_protector = challenge_protector
        self._verification_delivery = verification_delivery
        self._passwords = Argon2idPasswordVerifier()
        self._dummy_verifier = self._passwords.hash(secrets.token_urlsafe(32))

    def register(self, request: RegistrationRequest) -> AuthenticationSessionResponse:
        now = datetime.now(UTC)
        lookup = self._lookup(request.contact_kind, request.contact)
        password_verifier = self._passwords.hash(request.password)
        identity = Identity(
            identity_type=IdentityType.RIDER,
            status=AccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._composition.unit_of_work() as unit:
                self._enforce_rate_limit(unit, lookup, self._REGISTER_POLICY)
                unit.identities.create(identity)
                unit.password_credentials.create(
                    identity_id=identity.identity_id,
                    lookup_reference=lookup,
                    verifier=password_verifier,
                    scheme=self._passwords.scheme,
                    contact_kind=request.contact_kind,
                    created_at=now,
                )
                response = self._create_session(unit, identity, request, now)
                self._audit(
                    unit,
                    action="authentication.registration.succeeded",
                    outcome=AuditOutcome.SUCCESS,
                    identity=identity,
                    session_id=response.session_id,
                )
            return response
        except DuplicateAuthenticationIdentifier as error:
            self._audit_registration_conflict(lookup)
            raise RegistrationConflict("registration_unavailable") from error

    def sign_in(self, request: SignInRequest) -> AuthenticationSessionResponse:
        now = datetime.now(UTC)
        lookup = self._lookup(request.contact_kind, request.contact)
        denied = False
        response: AuthenticationSessionResponse | None = None
        with self._composition.unit_of_work() as unit:
            self._enforce_rate_limit(unit, lookup, self._SIGN_IN_POLICY)
            record = unit.password_credentials.find_by_lookup_reference(lookup)
            verifier = record.verifier if record is not None else self._dummy_verifier
            valid = self._passwords.verify(verifier, request.password)
            if (
                record is None
                or not valid
                or record.account_status is not AccountStatus.ACTIVE
                or record.identity_type is not IdentityType.RIDER
            ):
                denied = True
                self._audit(
                    unit,
                    action="authentication.sign_in.failed",
                    outcome=AuditOutcome.DENIED,
                    reason="invalid_credentials_or_state",
                )
            else:
                identity = unit.identities.get(record.identity_id)
                if identity is None:
                    raise RuntimeError("Credential identity is missing")
                if self._passwords.needs_upgrade(record.verifier):
                    unit.password_credentials.update_verifier(
                        lookup_reference=lookup,
                        verifier=self._passwords.hash(request.password),
                        scheme=self._passwords.scheme,
                        updated_at=now,
                    )
                response = self._create_session(unit, identity, request, now)
                self._audit(
                    unit,
                    action="authentication.sign_in.succeeded",
                    outcome=AuditOutcome.SUCCESS,
                    identity=identity,
                    session_id=response.session_id,
                )
        if denied or response is None:
            raise AuthenticationDenied("authentication_failed")
        return response

    def refresh(self, refresh_token: str) -> AuthenticationSessionResponse:
        now = datetime.now(UTC)
        family_id = self._family_id(refresh_token)
        presented_hash = self._token_hash(refresh_token)
        replacement = self._new_refresh_token(family_id)
        replacement_hash = self._token_hash(replacement)
        denied = False
        response: AuthenticationSessionResponse | None = None
        with self._composition.unit_of_work() as unit:
            self._enforce_rate_limit(unit, presented_hash, self._REFRESH_POLICY)
            try:
                result = unit.refresh_tokens.rotate(
                    family_id=family_id,
                    presented_hash=presented_hash,
                    replacement_hash=replacement_hash,
                    at=now,
                )
            except NoResultFound:
                self._audit(
                    unit,
                    action="authentication.refresh.denied",
                    outcome=AuditOutcome.DENIED,
                    reason="unknown_token_family",
                )
                denied = True
                result = None
            if result is None:
                pass
            elif result.outcome is not RefreshRotationOutcome.ROTATED:
                denied = True
                self._audit(
                    unit,
                    action=(
                        "authentication.refresh.replay_detected"
                        if result.outcome is RefreshRotationOutcome.REPLAY_DETECTED
                        else "authentication.refresh.denied"
                    ),
                    outcome=AuditOutcome.DENIED,
                    reason=result.outcome.value,
                    session_id=result.session_id,
                )
            else:
                session = unit.sessions.get(result.session_id)
                identity = (
                    unit.identities.get(session.identity_id)
                    if session is not None and session.identity_id is not None
                    else None
                )
                if (
                    session is None
                    or identity is None
                    or not session.is_active_at(now)
                    or identity.status is not AccountStatus.ACTIVE
                ):
                    denied = True
                    self._audit(
                        unit,
                        action="authentication.refresh.denied",
                        outcome=AuditOutcome.DENIED,
                        reason="subject_state_invalid",
                        session_id=result.session_id,
                    )
                else:
                    access_token, access_expiry = self._issuer.issue(
                        identity_id=identity.identity_id,
                        session_id=session.session_id,
                        identity_type=identity.identity_type,
                        assurance_level=AssuranceLevel.BASIC,
                        now=now,
                    )
                    response = AuthenticationSessionResponse(
                        identity_id=identity.identity_id,
                        session_id=session.session_id,
                        identity_type=identity.identity_type,
                        access_token=access_token,
                        access_expires_at=access_expiry,
                        refresh_token=replacement,
                        refresh_expires_at=session.expires_at,
                    )
                    self._audit(
                        unit,
                        action="authentication.session.refreshed",
                        outcome=AuditOutcome.SUCCESS,
                        identity=identity,
                        session_id=session.session_id,
                    )
        if denied or response is None:
            raise AuthenticationDenied("refresh_denied")
        return response

    def sign_out(self, *, identity_id: UUID, session_id: UUID) -> None:
        now = datetime.now(UTC)
        with self._composition.unit_of_work() as unit:
            session = unit.sessions.get(session_id)
            if session is None or session.identity_id != identity_id:
                raise AuthenticationDenied("session_not_found")
            unit.sessions.revoke(session_id, revoked_at=now, reason="user_sign_out")
            unit.refresh_tokens.revoke_for_session(session_id, at=now)
            self._audit(
                unit,
                action="authentication.session.signed_out",
                outcome=AuditOutcome.SUCCESS,
                identity_id=identity_id,
                session_id=session_id,
            )

    def sign_out_all(self, *, identity_id: UUID, session_id: UUID) -> int:
        now = datetime.now(UTC)
        with self._composition.unit_of_work() as unit:
            session = unit.sessions.get(session_id)
            if session is None or session.identity_id != identity_id:
                raise AuthenticationDenied("session_not_found")
            count = unit.sessions.revoke_all_for_identity(
                identity_id, revoked_at=now, reason="user_sign_out_all"
            )
            unit.refresh_tokens.revoke_all_for_identity(identity_id, at=now)
            self._audit(
                unit,
                action="authentication.sessions.all_signed_out",
                outcome=AuditOutcome.SUCCESS,
                identity_id=identity_id,
                session_id=session_id,
            )
        return count

    def prepare_recovery(self, kind: ContactKind, contact: str) -> None:
        """Enumeration-safe boundary; delivery activation is deliberately separate."""
        lookup = self._lookup(kind, normalize_contact(kind, contact))
        with self._composition.unit_of_work() as unit:
            self._enforce_rate_limit(unit, lookup, self._RECOVERY_POLICY)
            record = unit.password_credentials.find_by_lookup_reference(lookup)
            self._audit(
                unit,
                action="authentication.recovery.prepared",
                outcome=AuditOutcome.SUCCESS,
                identity_id=record.identity_id if record is not None else None,
            )

    def activation_progress(self, identity_id: UUID) -> IdentityActivationProgress:
        with self._composition.unit_of_work() as unit:
            statuses = unit.password_credentials.activation_progress(identity_id)
        return IdentityActivationProgress(
            identity_id=identity_id,
            **statuses,
            activated="verified" in statuses.values(),
        )

    def prepare_verification(
        self, *, identity_id: UUID, kind: ContactKind, contact: str
    ) -> VerificationPreparationResponse:
        if self._challenge_protector is None or self._verification_delivery is None:
            raise VerificationDeliveryUnavailable("verification_delivery_unavailable")
        normalized = normalize_contact(kind, contact)
        lookup = self._lookup(kind, normalized)
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=10)
        challenge_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        method_type = "email_verification" if kind is ContactKind.EMAIL else "phone_otp"
        with self._composition.unit_of_work() as unit:
            self._enforce_rate_limit(
                unit,
                hmac.digest(self._pepper, identity_id.bytes + lookup, "sha256"),
                self._VERIFICATION_POLICY,
            )
            method_id = unit.password_credentials.pending_verification_method(
                identity_id=identity_id,
                method_type=method_type,
                lookup_reference=lookup,
            )
            if method_id is None:
                raise AuthenticationDenied("verification_not_available")
            unit.authentication_challenges.create(
                AuthenticationChallenge(
                    challenge_id=challenge_id,
                    method_id=method_id,
                    purpose=(
                        ChallengePurpose.EMAIL_VERIFICATION
                        if kind is ContactKind.EMAIL
                        else ChallengePurpose.PHONE_OTP
                    ),
                    verifier=self._challenge_protector.protect(challenge_id, code),
                    expires_at=expires_at,
                    created_at=now,
                    max_attempts=5,
                )
            )
            self._audit(
                unit,
                action="authentication.verification.prepared",
                outcome=AuditOutcome.SUCCESS,
                identity_id=identity_id,
            )
        self._verification_delivery.deliver(
            kind=kind,
            destination=normalized,
            code=code,
            expires_at=expires_at,
        )
        return VerificationPreparationResponse(
            challenge_id=challenge_id, expires_at=expires_at
        )

    def complete_verification(
        self, *, identity_id: UUID, challenge_id: UUID, code: str
    ) -> IdentityActivationProgress:
        if self._challenge_protector is None:
            raise VerificationDeliveryUnavailable("verification_delivery_unavailable")
        now = datetime.now(UTC)
        denied = False
        with self._composition.unit_of_work() as unit:
            self._enforce_rate_limit(
                unit,
                hmac.digest(
                    self._pepper, identity_id.bytes + challenge_id.bytes, "sha256"
                ),
                self._VERIFICATION_POLICY,
            )
            challenge = unit.authentication_challenges.get(challenge_id)
            if (
                challenge is None
                or challenge.method_id is None
                or not unit.password_credentials.verification_method_belongs_to_identity(
                    challenge.method_id, identity_id=identity_id
                )
            ):
                denied = True
            else:
                matched = unit.authentication_challenges.verify(
                    challenge_id,
                    verifier=self._challenge_protector.protect(challenge_id, code),
                    at=now,
                )
                verified_identity = (
                    unit.password_credentials.mark_verification_method_verified(
                        challenge.method_id,
                        identity_id=identity_id,
                        verified_at=now,
                    )
                    if matched
                    else None
                )
                denied = verified_identity != identity_id
            self._audit(
                unit,
                action=(
                    "authentication.verification.failed"
                    if denied
                    else "authentication.verification.succeeded"
                ),
                outcome=AuditOutcome.DENIED if denied else AuditOutcome.SUCCESS,
                identity_id=identity_id,
                reason="invalid_or_expired_challenge" if denied else None,
            )
        if denied:
            raise AuthenticationDenied("verification_failed")
        return self.activation_progress(identity_id)

    def _create_session(
        self,
        unit: object,
        identity: Identity,
        request: RegistrationRequest | SignInRequest,
        now: datetime,
    ) -> AuthenticationSessionResponse:
        family_id = uuid4()
        session_id = uuid4()
        refresh_token = self._new_refresh_token(family_id)
        token_hash = self._token_hash(refresh_token)
        refresh_expiry = now + self._refresh_lifetime
        session = SessionRecord(
            session_id=session_id,
            subject_id=str(identity.identity_id),
            identity_id=identity.identity_id,
            device_id=request.device_id,
            device_fingerprint_ref=hmac.digest(
                self._pepper, request.device_id.bytes, "sha256"
            ),
            device_category=request.device_category,
            application_version=request.application_version,
            operating_system_family=request.operating_system_family,
            authentication_method="password",
            assurance_level=AssuranceLevel.BASIC.value,
            risk_state="standard",
            token_family_id=family_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=refresh_expiry,
        )
        unit.sessions.create(session)  # type: ignore[attr-defined]
        unit.refresh_tokens.create_family(  # type: ignore[attr-defined]
            family_id=family_id,
            identity_id=identity.identity_id,
            session_id=session_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=refresh_expiry,
        )
        access_token, access_expiry = self._issuer.issue(
            identity_id=identity.identity_id,
            session_id=session_id,
            identity_type=identity.identity_type,
            assurance_level=AssuranceLevel.BASIC,
            now=now,
        )
        return AuthenticationSessionResponse(
            identity_id=identity.identity_id,
            session_id=session_id,
            identity_type=identity.identity_type,
            access_token=access_token,
            access_expires_at=access_expiry,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expiry,
        )

    def _lookup(self, kind: ContactKind, contact: str) -> bytes:
        normalized = normalize_contact(kind, contact)
        return hmac.digest(
            self._pepper, f"{kind.value}:{normalized}".encode(), "sha256"
        )

    @staticmethod
    def _token_hash(token: str) -> bytes:
        return hashlib.sha256(token.encode()).digest()

    @staticmethod
    def _new_refresh_token(family_id: UUID) -> str:
        return f"{family_id}.{secrets.token_urlsafe(48)}"

    @staticmethod
    def _family_id(token: str) -> UUID:
        try:
            family, secret = token.split(".", 1)
            if len(secret) < 64:
                raise ValueError
            return UUID(family)
        except (ValueError, AttributeError) as error:
            raise AuthenticationDenied("refresh_denied") from error

    @staticmethod
    def _enforce_rate_limit(unit: object, key: bytes, policy: RateLimitPolicy) -> None:
        decision = unit.rate_limits.consume(  # type: ignore[attr-defined]
            key_hash=key, policy=policy
        )
        if not decision.allowed:
            unit.commit()  # type: ignore[attr-defined]
            raise AuthenticationRateLimited(decision.retry_after_seconds)

    def _audit_registration_conflict(self, lookup: bytes) -> None:
        with self._composition.unit_of_work() as unit:
            self._audit(
                unit,
                action="authentication.registration.denied",
                outcome=AuditOutcome.DENIED,
                reason="identifier_unavailable",
            )

    @staticmethod
    def _audit(
        unit: object,
        *,
        action: str,
        outcome: AuditOutcome,
        identity: Identity | None = None,
        identity_id: UUID | None = None,
        session_id: UUID | None = None,
        reason: str | None = None,
    ) -> None:
        resolved_identity_id = (
            identity.identity_id if identity is not None else identity_id
        )
        unit.audit_events.append(  # type: ignore[attr-defined]
            AuditEvent(
                actor_type=(
                    ActorType.RIDER if resolved_identity_id else ActorType.ANONYMOUS
                ),
                actor_id=str(resolved_identity_id) if resolved_identity_id else None,
                session_id=session_id,
                action=action,
                resource_type="authentication",
                resource_id=(
                    str(resolved_identity_id) if resolved_identity_id else None
                ),
                outcome=outcome,
                reason=reason,
                correlation_id=uuid4(),
                source_module="identity",
                safe_metadata={"category": "authentication"},
            )
        )
