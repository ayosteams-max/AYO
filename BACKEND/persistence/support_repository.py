from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.tables import (
    support_ai_interactions,
    support_case_events,
    support_case_messages,
    support_cases,
)
from BACKEND.support.models import (
    MessageVisibility,
    SupportAIInteraction,
    SupportCase,
    SupportCaseEvent,
    SupportMessage,
)


def _model(model_type, row: Mapping[str, Any]):
    return model_type.model_validate(dict(row))


class PostgresSupportRepository:
    """Transactional support persistence; event streams expose append only."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_case(self, case: SupportCase) -> tuple[SupportCase, bool]:
        statement = (
            postgres_insert(support_cases)
            .values(**case.model_dump())
            .on_conflict_do_nothing(index_elements=[support_cases.c.idempotency_key])
            .returning(support_cases)
        )
        row = self._connection.execute(statement).mappings().one_or_none()
        if row is not None:
            return _model(SupportCase, row), True
        existing = (
            self._connection.execute(
                select(support_cases).where(
                    support_cases.c.idempotency_key == case.idempotency_key
                )
            )
            .mappings()
            .one()
        )
        return _model(SupportCase, existing), False

    def get_case(self, case_id: UUID) -> SupportCase | None:
        row = (
            self._connection.execute(
                select(support_cases).where(support_cases.c.case_id == case_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(SupportCase, row)

    def save_case(self, case: SupportCase, *, expected_version: int) -> SupportCase:
        values = case.model_dump(exclude={"case_id", "version"})
        row = (
            self._connection.execute(
                update(support_cases)
                .where(
                    support_cases.c.case_id == case.case_id,
                    support_cases.c.version == expected_version,
                )
                .values(**values, version=expected_version + 1)
                .returning(support_cases)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Support case changed concurrently.")
        return _model(SupportCase, row)

    def append_event(self, event: SupportCaseEvent) -> None:
        self._connection.execute(
            insert(support_case_events).values(**event.model_dump())
        )

    def append_message(self, message: SupportMessage) -> None:
        self._connection.execute(
            insert(support_case_messages).values(**message.model_dump())
        )

    def list_messages(
        self, case_id: UUID, *, include_internal: bool
    ) -> list[SupportMessage]:
        statement = select(support_case_messages).where(
            support_case_messages.c.case_id == case_id
        )
        if not include_internal:
            statement = statement.where(
                support_case_messages.c.visibility
                == MessageVisibility.CUSTOMER_VISIBLE.value
            )
        rows = self._connection.execute(
            statement.order_by(support_case_messages.c.created_at)
        ).mappings()
        return [_model(SupportMessage, row) for row in rows]

    def append_ai_interaction(self, interaction: SupportAIInteraction) -> None:
        self._connection.execute(
            insert(support_ai_interactions).values(**interaction.model_dump())
        )
