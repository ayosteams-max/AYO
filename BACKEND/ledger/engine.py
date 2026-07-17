import hashlib
import json
from typing import Any

from BACKEND.ledger.models import LedgerJournal
from BACKEND.pricing.engine import PricingConflict


class LedgerConflict(PricingConflict):
    """Ledger foundation conflict using existing conflict semantics."""


def canonical_posting_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def deterministic_replay_view(journal: LedgerJournal) -> dict[str, Any]:
    entries = sorted(journal.entries, key=lambda item: item.line_index)
    return {
        "journal_id": str(journal.journal_id),
        "book_id": str(journal.book_id),
        "business_event_type": journal.business_event_type,
        "business_event_id": str(journal.business_event_id),
        "operation": journal.operation,
        "idempotency_key": journal.idempotency_key,
        "actor_identity_id": str(journal.actor_identity_id),
        "source_system": journal.source_system,
        "reason_code": journal.reason_code,
        "traceability": journal.traceability.model_dump(mode="json"),
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "effective_at": journal.effective_at.isoformat(),
        "recorded_at": journal.recorded_at.isoformat(),
        "correlation_id": str(journal.correlation_id),
        "causation_id": str(journal.causation_id),
        "audit_reference": str(journal.audit_reference),
    }
