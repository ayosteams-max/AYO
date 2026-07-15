from typing import Protocol
from uuid import UUID

from BACKEND.support.models import (
    SupportAIInteraction,
    SupportCase,
    SupportCaseEvent,
    SupportMessage,
)


class SupportRepository(Protocol):
    def create_case(self, case: SupportCase) -> tuple[SupportCase, bool]: ...

    def get_case(self, case_id: UUID) -> SupportCase | None: ...

    def save_case(self, case: SupportCase, *, expected_version: int) -> SupportCase: ...

    def append_event(self, event: SupportCaseEvent) -> None: ...

    def append_message(self, message: SupportMessage) -> None: ...

    def list_messages(
        self, case_id: UUID, *, include_internal: bool
    ) -> list[SupportMessage]: ...

    def append_ai_interaction(self, interaction: SupportAIInteraction) -> None: ...
