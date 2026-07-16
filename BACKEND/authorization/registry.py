from types import MappingProxyType

# Infrastructure permissions only. Product and operations role matrices require
# explicit CEO/CTO policy approval and are not seeded by this mission.
PERMISSION_REGISTRY = MappingProxyType(
    {
        "authorization.permissions.read": "Read the authorization permission registry.",
        "authorization.roles.read": "Read authorization roles and their grants.",
        "authorization.roles.manage": "Create roles and manage role permissions.",
        "authorization.assignments.read": "Read identity role assignments.",
        "authorization.assignments.manage": "Assign and revoke identity roles.",
        "support.case.create": "Create a support case with approved structured details.",
        "support.case.read_assigned": "Read only support cases assigned to the service identity.",
        "support.case.update": "Update approved fields on an assigned support case.",
        "support.case.escalate": "Escalate a support case to trained human support.",
        "support.trip.read_limited": "Read the minimum approved trip support view.",
        "support.payment.read_status": "Read payment status without credentials or mutation authority.",
        "support.account.read_limited": "Read the minimum approved account support view.",
        "support.guidance.provide": "Provide approved low-risk support guidance.",
        "support.queue.general.access": "Access support cases assigned to the general queue.",
        "support.queue.safety.access": "Access restricted safety support cases.",
        "support.queue.fraud.access": "Access restricted fraud support cases.",
        "support.queue.finance.access": "Access restricted finance support cases.",
        "support.queue.identity.access": "Access restricted identity support cases.",
        "support.queue.legal.access": "Access restricted legal support cases.",
        "dispatch.rider.request": "Create and recover the authenticated rider's rides.",
        "dispatch.driver.offer.respond": "Read and respond to the authenticated driver's offers.",
        "dispatch.worker.recover": "Run bounded server-side dispatch recovery.",
        "dispatch.admin.health.read": "Read internal dispatch worker health.",
        "scheduled.rider.create": "Create a scheduled reservation as the authenticated booker.",
        "scheduled.reservation.read": "Read an owned scheduled reservation.",
        "scheduled.reservation.manage": "Update, confirm or cancel an owned reservation.",
        "scheduled.driver.commitment.respond": "Respond to an authenticated driver's commitment.",
        "scheduled.support.handoff": "Create an authorized assisted-booking support handoff.",
        "scheduled.worker.run": "Run bounded scheduled-dispatch workers.",
        "scheduled.worker.health.read": "Read scheduled worker health.",
        "active_ride.read": "Read an owned active ride projection and event stream.",
        "active_ride.rider.command": "Submit an authenticated rider active-ride command.",
        "active_ride.driver.command": "Submit an assigned driver active-ride command.",
        "active_ride.worker.run": "Run bounded active-ride recovery workers.",
        "active_ride.worker.health.read": "Read active-ride worker health.",
        "arrival_waiting.read": "Read an owned arrival and waiting projection.",
        "arrival_waiting.rider.command": "Submit an owned rider arrival/waiting command.",
        "arrival_waiting.driver.command": "Submit an assigned driver arrival/waiting command.",
        "arrival_waiting.worker.run": "Run bounded arrival/waiting recovery work.",
        "driver_trust.read_own": "Read the authenticated driver's onboarding projection.",
        "driver_trust.evidence.read_own": "Read privacy-minimised own evidence metadata.",
        "driver_trust.evidence.read_sensitive": "Read separately authorized sensitive evidence metadata.",
        "driver_trust.review": "Perform an authorized operations review decision.",
        "driver_trust.appeal.review": "Review a linked driver identity appeal.",
        "ride_request.create": "Create an authenticated rider's Immediate Standard request.",
        "ride_request.read_own": "Read the authenticated rider's canonical request.",
        "ride_request.cancel_own": "Cancel the authenticated rider's pre-dispatch request.",
        "ride_request.support.read": "Read an explicitly authorized support projection.",
    }
)

AI_SUPPORT_PERMISSION_SET = frozenset(
    {
        "support.case.create",
        "support.case.read_assigned",
        "support.case.update",
        "support.case.escalate",
        "support.trip.read_limited",
        "support.payment.read_status",
        "support.account.read_limited",
        "support.guidance.provide",
    }
)
