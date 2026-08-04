from types import MappingProxyType

REFUND_PERMISSION_REGISTRY = MappingProxyType(
    {
        "refund.request.create": "Create an immutable refund or adjustment request for an owned ride payment.",
        "refund.review.perform": "Perform support review transitions on a refund request.",
        "refund.investigation.perform": "Record risk investigation findings and evidence on a refund request.",
        "refund.approve": "Approve refund requests for finance-authorized outcomes.",
        "refund.schedule": "Schedule approved refund requests for bounded workflow completion.",
        "refund.workflow.run": "Execute bounded service-side completion transitions.",
        "refund.trace.read": "Read immutable refund requests, decisions, authorizations, and evidence.",
        "support.refund.read_status": "Read refund request status without mutation authority.",
    }
)
