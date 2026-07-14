import json
import logging
from datetime import datetime, timezone
from typing import Any


class StructuredJsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for safe operational events."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "ayo_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, separators=(",", ":"), default=str)


def database_event(
    logger: logging.Logger,
    event: str,
    outcome: str,
    duration_ms: float,
    **safe_fields: str | int | float | bool | None,
) -> None:
    logger.info(
        "database_operation",
        extra={
            "ayo_fields": {
                "event": event,
                "outcome": outcome,
                "duration_ms": round(duration_ms, 3),
                **safe_fields,
            }
        },
    )
