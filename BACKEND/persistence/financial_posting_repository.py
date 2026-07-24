import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.financial_posting.engine import (
    FinancialPostingConflict,
    canonical_posting_hash,
)
from BACKEND.financial_posting.models import FinancialPosting, FinancialPostingLine
from BACKEND.persistence.tables import (
    financial_posting_events,
    financial_posting_idempotency,
    financial_posting_lines,
    financial_posting_outbox,
    financial_postings,
)


def _posting(row: Any) -> FinancialPosting:
    return FinancialPosting.model_validate(dict(row))


def _line(row: Any) -> FinancialPostingLine:
    return FinancialPostingLine.model_validate(dict(row))


class PostgresFinancialPostingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, str],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = canonical_posting_hash(payload)
        row = self._connection.execute(
            pg_insert(financial_posting_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(financial_posting_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(financial_posting_idempotency).where(
                    financial_posting_idempotency.c.actor_id == actor_id,
                    financial_posting_idempotency.c.operation == operation,
                    financial_posting_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise FinancialPostingConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def get_posting(self, posting_id: UUID) -> FinancialPosting | None:
        row = (
            self._connection.execute(
                select(financial_postings).where(
                    financial_postings.c.posting_id == posting_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _posting(row)

    def list_lines(self, posting_id: UUID) -> tuple[FinancialPostingLine, ...]:
        rows = self._connection.execute(
            select(financial_posting_lines)
            .where(financial_posting_lines.c.posting_id == posting_id)
            .order_by(financial_posting_lines.c.line_index)
        ).mappings()
        return tuple(_line(row) for row in rows)

    def create_posting(
        self,
        posting: FinancialPosting,
        lines: tuple[FinancialPostingLine, ...],
    ) -> FinancialPosting:
        self._connection.execute(
            insert(financial_postings).values(**posting.model_dump(mode="json"))
        )
        self._connection.execute(
            insert(financial_posting_lines),
            [item.model_dump(mode="json") for item in lines],
        )
        event_id = uuid4()
        self._connection.execute(
            insert(financial_posting_events).values(
                event_id=event_id,
                aggregate_type="financial_posting",
                aggregate_id=posting.posting_id,
                event_type="financial_posting.posted",
                schema_version=1,
                safe_payload={
                    "posting_id": str(posting.posting_id),
                    "source_type": posting.source_type.value,
                    "source_id": str(posting.source_id),
                    "currency": posting.currency,
                    "total_debit_minor": posting.total_debit_minor,
                    "total_credit_minor": posting.total_credit_minor,
                    "ledger_journal_id": str(posting.ledger_journal_id),
                    "wallet_entry_id": str(posting.wallet_entry_id),
                },
                replay_payload={
                    "posting": posting.model_dump(mode="json"),
                    "lines": [item.model_dump(mode="json") for item in lines],
                },
                occurred_at=posting.created_at,
                correlation_id=posting.correlation_id,
                causation_id=posting.causation_id,
            )
        )
        self._connection.execute(
            insert(financial_posting_outbox).values(
                message_id=uuid4(),
                event_id=event_id,
                event_type="financial_posting.posted",
                safe_payload={
                    "posting_id": str(posting.posting_id),
                    "source_type": posting.source_type.value,
                    "ledger_journal_id": str(posting.ledger_journal_id),
                    "wallet_entry_id": str(posting.wallet_entry_id),
                },
                occurred_at=posting.created_at,
                available_at=posting.created_at,
                attempt_count=0,
            )
        )
        return posting

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        return canonical_posting_hash(json.loads(json.dumps(payload)))
