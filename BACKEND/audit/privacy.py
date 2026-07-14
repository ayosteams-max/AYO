import re
from collections.abc import Mapping

from pydantic_core import PydanticCustomError

type SafeAuditValue = str | int | bool
type SafeAuditMetadata = dict[str, SafeAuditValue]

SAFE_METADATA_FIELDS = frozenset(
    {
        "category",
        "channel",
        "error_category",
        "operation",
        "policy_version",
        "risk_level",
        "state_from",
        "state_to",
    }
)
PROHIBITED_KEY_PATTERN = re.compile(
    r"password|passcode|otp|token|secret|private.?key|credential|authorization|"
    r"database.?url|phone|email|government|passport|national.?id|device.?id|"
    r"location|latitude|longitude|request.?body|response.?body",
    re.IGNORECASE,
)
SAFE_STRING_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def validate_safe_metadata(value: object) -> SafeAuditMetadata:
    if not isinstance(value, Mapping):
        raise PydanticCustomError("audit_metadata_type", "Metadata must be an object")
    if len(value) > 12:
        raise PydanticCustomError(
            "audit_metadata_size", "Metadata exceeds the allowed field count"
        )

    result: SafeAuditMetadata = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if PROHIBITED_KEY_PATTERN.search(key):
            raise PydanticCustomError(
                "audit_metadata_prohibited", "Metadata contains a prohibited field"
            )
        if key not in SAFE_METADATA_FIELDS:
            raise PydanticCustomError(
                "audit_metadata_not_allowed", "Metadata field is not allowlisted"
            )
        if not isinstance(raw_value, str | int | bool) or isinstance(raw_value, float):
            raise PydanticCustomError(
                "audit_metadata_value", "Metadata values must be safe scalar values"
            )
        if isinstance(raw_value, str) and not SAFE_STRING_PATTERN.fullmatch(raw_value):
            raise PydanticCustomError(
                "audit_metadata_value", "Metadata string is not a safe category value"
            )
        result[key] = raw_value
    return result
