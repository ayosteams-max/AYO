from types import MappingProxyType

SETTLEMENT_PERMISSION_REGISTRY = MappingProxyType(
    {
        "settlement.batch.create": "Create an immutable settlement reconciliation batch.",
        "settlement.collect.run": "Collect provider-neutral batch items for reconciliation.",
        "settlement.reconcile.run": "Run bounded reconciliation and exception classification.",
        "settlement.ready.approve": "Approve a balanced batch for settlement readiness.",
        "settlement.exception.investigate": "Investigate reconciliation exceptions and record manual review outcomes.",
        "settlement.trace.read": "Read immutable settlement and reconciliation traces.",
        "support.settlement.read_status": "Read settlement and reconciliation status without mutation authority.",
    }
)
