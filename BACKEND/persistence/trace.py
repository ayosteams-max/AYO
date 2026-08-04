from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TraceContext:
    correlation_id: UUID
    request_id: UUID
    command_id: UUID | None = None
    causation_id: UUID | None = None

    @classmethod
    def new(cls, *, request_id: UUID | None = None) -> "TraceContext":
        return cls(correlation_id=uuid4(), request_id=request_id or uuid4())

    def child(self, *, command_id: UUID | None = None) -> "TraceContext":
        return TraceContext(
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            command_id=command_id,
            causation_id=self.command_id or self.causation_id,
        )


_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "ayo_persistence_trace_context", default=None
)


def current_trace_context() -> TraceContext:
    context = _trace_context.get()
    if context is None:
        raise RuntimeError("Persistence trace context is not bound.")
    return context


@contextmanager
def bind_trace_context(context: TraceContext) -> Iterator[TraceContext]:
    token: Token[TraceContext | None] = _trace_context.set(context)
    try:
        yield context
    finally:
        _trace_context.reset(token)
