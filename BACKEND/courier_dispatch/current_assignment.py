from typing import Any

from BACKEND.courier_dispatch.models import (
    CourierAssignmentState,
    CourierDispatchState,
)


def matches_current_assignment(unit: Any, pickup: Any, *, lock: bool) -> bool:
    """Check the dispatch-owned assignment bound into one courier pickup."""
    dispatch = unit.courier_dispatch.get(pickup.dispatch_id, lock=lock)
    assignment = unit.courier_dispatch.get_assignment(pickup.assignment_id, lock=lock)
    return bool(
        dispatch is not None
        and dispatch.state is CourierDispatchState.ASSIGNED
        and dispatch.order_id == pickup.order_id
        and dispatch.merchant_id == pickup.merchant_id
        and dispatch.active_assignment_id == pickup.assignment_id
        and dispatch.assigned_courier_identity_id == pickup.assigned_courier_identity_id
        and assignment is not None
        and assignment.dispatch_id == pickup.dispatch_id
        and assignment.courier_identity_id == pickup.assigned_courier_identity_id
        and assignment.state is CourierAssignmentState.ASSIGNED
        and assignment.version == pickup.assignment_version
    )
