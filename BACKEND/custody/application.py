import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.custody.engine import CustodyConflict, target_state
from BACKEND.custody.models import (
    CustodyAction,
    CustodyView,
    IssuedPickupCode,
    VerificationMethod,
)
from BACKEND.merchant.models import MerchantState


class CustodyApplication:
    def __init__(
        self,
        composition: Any,
        *,
        verification_pepper: bytes,
        challenge_minutes: int = 10,
    ) -> None:
        if len(verification_pepper) < 32:
            raise ValueError("custody_verification_pepper_too_short")
        self._composition = composition
        self._pepper = verification_pepper
        self._challenge_minutes = challenge_minutes

    def activate_from_waiting(self, *, pickup_id: UUID, at: datetime) -> CustodyView:
        with self._composition.unit_of_work() as unit:
            return unit.custody.activate(pickup_id=pickup_id, at=at)

    def merchant_detail(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, order_id: UUID
    ) -> CustodyView:
        with self._composition.unit_of_work() as unit:
            self._merchant(unit, subject, merchant_id)
            value = unit.custody.get_by_order(order_id)
            if value is None or value.custody.merchant_id != merchant_id:
                raise CustodyConflict("custody_not_found")
            return value

    def seal(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        custody_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> IssuedPickupCode:
        code = (
            base64.urlsafe_b64encode(
                hmac.new(
                    self._pepper,
                    f"{custody_id}:{idempotency_key}".encode(),
                    hashlib.sha256,
                ).digest()
            )
            .decode()
            .rstrip("=")
        )
        digest = self._digest(code)
        with self._composition.unit_of_work() as unit:
            self._merchant(unit, subject, merchant_id)
            current = unit.custody.get(custody_id, lock=True)
            if current is None or current.merchant_id != merchant_id:
                raise CustodyConflict("custody_not_found")
            replay = unit.custody.reserve(
                actor_id=subject.identity_id,
                custody_id=custody_id,
                key=idempotency_key,
                payload=f"seal:{expected_version}",
                at=at,
            )
            if replay is not None:
                return IssuedPickupCode(view=replay, display_code=code)
            if current.version != expected_version:
                raise CustodyConflict("custody_version_conflict")
            view = unit.custody.seal(
                current,
                target=target_state(current.state, CustodyAction.SEAL),
                actor_id=subject.identity_id,
                code_hash=digest,
                expires_at=at + timedelta(minutes=self._challenge_minutes),
                key=idempotency_key,
                at=at,
            )
            return IssuedPickupCode(view=view, display_code=code)

    def command(
        self,
        subject: AuthorizationSubject,
        *,
        custody_id: UUID,
        expected_version: int,
        action: CustodyAction,
        idempotency_key: str,
        at: datetime,
        code: str | None = None,
        method: VerificationMethod | None = None,
        merchant_id: UUID | None = None,
    ) -> CustodyView:
        with self._composition.unit_of_work() as unit:
            current = unit.custody.get(custody_id, lock=True)
            if current is None:
                raise CustodyConflict("custody_not_found")
            if action is CustodyAction.RELEASE:
                if merchant_id is None:
                    raise CustodyConflict("merchant_required")
                self._merchant(unit, subject, merchant_id)
                if current.merchant_id != merchant_id:
                    raise CustodyConflict("access_denied")
            elif current.courier_identity_id != subject.identity_id:
                raise CustodyConflict("access_denied")
            replay = unit.custody.reserve(
                actor_id=subject.identity_id,
                custody_id=custody_id,
                key=idempotency_key,
                payload=f"{action.value}:{expected_version}:{method or ''}:{self._digest(code or '')}",
                at=at,
            )
            if replay is not None:
                return replay
            if current.version != expected_version:
                raise CustodyConflict("custody_version_conflict")
            if action is CustodyAction.VERIFY:
                if not code or method is None:
                    raise CustodyConflict("verification_evidence_required")
                return unit.custody.verify(
                    current,
                    target=target_state(current.state, action),
                    actor_id=subject.identity_id,
                    code_hash=self._digest(code),
                    method=method,
                    key=idempotency_key,
                    at=at,
                )
            if action not in (CustodyAction.RELEASE, CustodyAction.ACCEPT):
                raise CustodyConflict("unsupported_custody_action")
            return unit.custody.transition(
                current,
                target=target_state(current.state, action),
                actor_id=subject.identity_id,
                key=idempotency_key,
                at=at,
            )

    def _digest(self, code: str) -> str:
        return hmac.new(self._pepper, code.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _merchant(unit: Any, subject: AuthorizationSubject, merchant_id: UUID) -> None:
        merchant = unit.merchants.get_profile(merchant_id, lock=False)
        if merchant is None or merchant.owner_identity_id != subject.identity_id:
            raise CustodyConflict("access_denied")
        if merchant.state is not MerchantState.APPROVED:
            raise CustodyConflict("merchant_unavailable")
