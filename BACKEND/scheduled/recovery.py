from datetime import datetime

from BACKEND.scheduled.models import (
    TERMINAL_STATES,
    RecoveryAction,
    RecoveryDecision,
    ReservationCheckpoint,
    ReservationPolicy,
    ReservationState,
    ScheduledReservation,
)


def recover_checkpoint(
    reservation: ScheduledReservation,
    checkpoint: ReservationCheckpoint,
    policy: ReservationPolicy,
    *,
    now: datetime,
) -> RecoveryDecision:
    if checkpoint.reservation_id != reservation.reservation_id:
        raise ValueError("Checkpoint belongs to another reservation")
    if reservation.state in TERMINAL_STATES or checkpoint.completed_at is not None:
        return RecoveryDecision(
            reservation_id=reservation.reservation_id,
            action=RecoveryAction.WAIT,
            policy_version=policy.version,
            reason_codes=("checkpoint_not_actionable",),
        )
    if checkpoint.attempt_count >= policy.checkpoint_retry_limit:
        return RecoveryDecision(
            reservation_id=reservation.reservation_id,
            action=RecoveryAction.OPERATIONAL_REVIEW,
            policy_version=policy.version,
            reason_codes=("checkpoint_retry_limit_reached",),
        )
    if checkpoint.due_at > now:
        return RecoveryDecision(
            reservation_id=reservation.reservation_id,
            action=RecoveryAction.WAIT,
            policy_version=policy.version,
            reason_codes=("checkpoint_not_due",),
        )
    action_by_state = {
        ReservationState.ACCEPTED: RecoveryAction.PLAN,
        ReservationState.PLANNING: RecoveryAction.COMMIT,
        ReservationState.DRIVER_COMMITTED: RecoveryAction.REVALIDATE,
        ReservationState.REVALIDATING: RecoveryAction.FALLBACK_DISPATCH,
        ReservationState.REASSIGNING: RecoveryAction.FALLBACK_DISPATCH,
    }
    action = action_by_state.get(reservation.state, RecoveryAction.OPERATIONAL_REVIEW)
    return RecoveryDecision(
        reservation_id=reservation.reservation_id,
        action=action,
        policy_version=policy.version,
        reason_codes=("restart_safe_checkpoint_recovered",),
    )
