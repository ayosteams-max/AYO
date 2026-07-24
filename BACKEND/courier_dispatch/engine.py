from dataclasses import dataclass
from datetime import datetime, timedelta

from BACKEND.courier_dispatch.models import (
    CourierDispatchAction,
    CourierDispatchState,
    CourierEligibilityEvidence,
    EligibilityEvidenceType,
)


class CourierDispatchConflict(ValueError):
    pass


@dataclass(frozen=True)
class DispatchPolicy:
    code: str = "AYO_COURIER_DISPATCH_POLICY_V1"
    version: int = 1
    offer_window_seconds: int = 120

    def evaluate(
        self,
        evidence: tuple[CourierEligibilityEvidence, ...],
        *,
        at: datetime,
    ) -> tuple[CourierEligibilityEvidence, ...]:
        required = set(EligibilityEvidenceType)
        by_type = {item.evidence_type: item for item in evidence}
        if set(by_type) != required or len(evidence) != len(required):
            raise CourierDispatchConflict("courier_eligibility_evidence_incomplete")
        if any(
            not item.eligible or item.observed_at > at or item.valid_until <= at
            for item in evidence
        ):
            raise CourierDispatchConflict("courier_ineligible")
        return tuple(sorted(evidence, key=lambda item: item.evidence_type.value))

    def expires_at(self, at: datetime) -> datetime:
        return at + timedelta(seconds=self.offer_window_seconds)


def target_state(
    state: CourierDispatchState, action: CourierDispatchAction
) -> CourierDispatchState:
    transitions = {
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.OFFER,
        ): CourierDispatchState.OFFERED,
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.ACCEPT,
        ): CourierDispatchState.ASSIGNED,
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.DECLINE,
        ): CourierDispatchState.WAITING,
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.EXPIRE,
        ): CourierDispatchState.WAITING,
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.REVOKE,
        ): CourierDispatchState.WAITING,
        (
            CourierDispatchState.ASSIGNED,
            CourierDispatchAction.RELEASE,
        ): CourierDispatchState.WAITING,
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.CANCEL,
        ): CourierDispatchState.CANCELLED,
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.CANCEL,
        ): CourierDispatchState.CANCELLED,
        (
            CourierDispatchState.ASSIGNED,
            CourierDispatchAction.CANCEL,
        ): CourierDispatchState.CANCELLED,
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.CONCLUDE_UNFULFILLED,
        ): CourierDispatchState.UNFULFILLED,
    }
    try:
        return transitions[(state, action)]
    except KeyError as error:
        raise CourierDispatchConflict("invalid_courier_dispatch_transition") from error
