from dataclasses import dataclass

from BACKEND.identity.compatibility_models import LegacySemantic
from BACKEND.persistence.tables import metadata


@dataclass(frozen=True, slots=True)
class LegacyReference:
    table: str
    column: str
    semantic: LegacySemantic
    rationale: str


_BUSINESS_PREFIXES = (
    "rider_",
    "driver_",
    "courier_",
    "merchant_",
    "customer_",
    "passenger_",
    "payer_",
    "booker_",
    "representative_",
)
_AUDIT_MARKERS = (
    "actor_",
    "author_",
    "created_by_",
    "changed_by_",
    "recorded_by_",
    "reviewed_by_",
    "requested_by_",
    "decided_by_",
    "approved_by_",
    "authorized_by_",
    "assigned_by_",
    "revoked_by_",
    "recommended_by_",
    "resolved_by_",
    "raised_by_",
    "prepared_by_",
    "evaluated_by_",
    "published_by_",
)


def classify_reference(table: str, column: str) -> tuple[LegacySemantic, str]:
    if table == "identities":
        return LegacySemantic.AMBIGUOUS, "mixed legacy identity authority"
    if table in {
        "identity_authentication_methods",
        "identity_devices",
        "token_families",
        "sessions",
        "recovery_cases",
        "authentication_challenges",
    }:
        return LegacySemantic.AUTHENTICATION_ACTOR, "authentication-owned legacy link"
    if table == "identity_role_assignments" and column == "identity_id":
        return LegacySemantic.AUTHORIZATION_PRINCIPAL, "RBAC assignment subject"
    if column.startswith(_BUSINESS_PREFIXES):
        return LegacySemantic.BUSINESS_PARTICIPANT, "domain-labelled participant"
    if column.startswith("owner_"):
        return LegacySemantic.RESOURCE_OWNER, "owning-domain relationship"
    if column.startswith(_AUDIT_MARKERS) or column.endswith("_by_identity_id"):
        return LegacySemantic.AUDIT_ACTOR, "historical action attribution"
    if column in {"identity_id", "target_identity_id", "recipient_identity_id"}:
        return LegacySemantic.AMBIGUOUS, "meaning depends on bounded context"
    return LegacySemantic.AMBIGUOUS, "no safe semantic proof"


def legacy_reference_inventory() -> tuple[LegacyReference, ...]:
    references: list[LegacyReference] = []
    for table in metadata.tables.values():
        for column in table.columns:
            if "identity_id" not in column.name and not (
                table.name == "identities" and column.name == "identity_type"
            ):
                continue
            semantic, rationale = classify_reference(table.name, column.name)
            references.append(
                LegacyReference(table.name, column.name, semantic, rationale)
            )
    return tuple(sorted(references, key=lambda item: (item.table, item.column)))
