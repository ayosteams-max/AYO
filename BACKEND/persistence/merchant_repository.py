import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.merchant.engine import MerchantConflict
from BACKEND.merchant.models import (
    CatalogueItem,
    MerchantBranch,
    MerchantProfile,
    PartnerProgram,
    ProgramEnrollment,
    VerificationEvidence,
)
from BACKEND.persistence.tables import (
    merchant_assistance,
    merchant_branches,
    merchant_catalogue_items,
    merchant_idempotency,
    merchant_outbox,
    merchant_partner_programs,
    merchant_profiles,
    merchant_program_enrollments,
    merchant_verifications,
)


def _model(model, row):
    return model.model_validate(dict(row))


class PostgresMerchantRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        actor: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        candidate: UUID,
        at: datetime,
    ) -> UUID:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        found = self._connection.execute(
            pg_insert(merchant_idempotency)
            .values(
                actor_identity_id=actor,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=candidate,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(merchant_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if found is not None:
            return cast(UUID, found)
        existing = (
            self._connection.execute(
                select(merchant_idempotency).where(
                    merchant_idempotency.c.actor_identity_id == actor,
                    merchant_idempotency.c.operation == operation,
                    merchant_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise MerchantConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def create_profile(self, value: MerchantProfile) -> MerchantProfile:
        existing = self.get_profile(value.merchant_id)
        if existing is not None:
            return existing
        self._connection.execute(
            insert(merchant_profiles).values(**value.model_dump(mode="json"))
        )
        self.event(
            value.merchant_id,
            "merchant.created",
            {"merchant_id": str(value.merchant_id), "state": value.state.value},
            value.created_at,
        )
        return value

    def get_profile(
        self, merchant_id: UUID, *, lock: bool = False
    ) -> MerchantProfile | None:
        query = select(merchant_profiles).where(
            merchant_profiles.c.merchant_id == merchant_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _model(MerchantProfile, row)

    def list_owned(
        self, owner_id: UUID, limit: int = 50
    ) -> tuple[MerchantProfile, ...]:
        rows = self._connection.execute(
            select(merchant_profiles)
            .where(merchant_profiles.c.owner_identity_id == owner_id)
            .order_by(merchant_profiles.c.created_at)
            .limit(limit)
        ).mappings()
        return tuple(_model(MerchantProfile, row) for row in rows)

    def create_branch(self, value: MerchantBranch) -> MerchantBranch:
        self._connection.execute(
            insert(merchant_branches).values(**value.model_dump(mode="json"))
        )
        self.event(
            value.merchant_id,
            "merchant.branch.created",
            {"branch_id": str(value.branch_id)},
            value.created_at,
        )
        return value

    def branch_count(self, merchant_id: UUID) -> int:
        return int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_branches)
                .where(merchant_branches.c.merchant_id == merchant_id)
            ).scalar_one()
        )

    def operating_hours_count(self, merchant_id: UUID) -> int:
        return int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_branches)
                .where(
                    merchant_branches.c.merchant_id == merchant_id,
                    merchant_branches.c.active.is_(True),
                    merchant_branches.c.operating_hours != {},
                )
            ).scalar_one()
        )

    def get_branch_merchant(self, branch_id: UUID) -> UUID | None:
        return self._connection.execute(
            select(merchant_branches.c.merchant_id).where(
                merchant_branches.c.branch_id == branch_id
            )
        ).scalar_one_or_none()

    def upsert_verification(self, value: VerificationEvidence) -> VerificationEvidence:
        row = (
            self._connection.execute(
                pg_insert(merchant_verifications)
                .values(**value.model_dump(mode="json"))
                .on_conflict_do_update(
                    index_elements=[
                        merchant_verifications.c.merchant_id,
                        merchant_verifications.c.kind,
                    ],
                    set_={
                        "state": value.state.value,
                        "opaque_reference": value.opaque_reference,
                        "expires_at": value.expires_at,
                        "submitted_at": value.submitted_at,
                        "reviewed_at": value.reviewed_at,
                        "reviewed_by_identity_id": value.reviewed_by_identity_id,
                        "reason_code": value.reason_code,
                    },
                )
                .returning(merchant_verifications)
            )
            .mappings()
            .one()
        )
        self.event(
            value.merchant_id,
            "merchant.verification.submitted",
            {"kind": value.kind.value, "state": value.state.value},
            value.submitted_at,
        )
        return _model(VerificationEvidence, row)

    def verifications(self, merchant_id: UUID) -> tuple[VerificationEvidence, ...]:
        rows = self._connection.execute(
            select(merchant_verifications)
            .where(merchant_verifications.c.merchant_id == merchant_id)
            .order_by(merchant_verifications.c.kind)
        ).mappings()
        return tuple(_model(VerificationEvidence, row) for row in rows)

    def get_verification(
        self, evidence_id: UUID, *, lock: bool = False
    ) -> VerificationEvidence | None:
        query = select(merchant_verifications).where(
            merchant_verifications.c.evidence_id == evidence_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _model(VerificationEvidence, row)

    def review_verification(self, value: VerificationEvidence) -> VerificationEvidence:
        row = (
            self._connection.execute(
                update(merchant_verifications)
                .where(
                    merchant_verifications.c.evidence_id == value.evidence_id,
                    merchant_verifications.c.state == "submitted",
                )
                .values(
                    state=value.state.value,
                    reviewed_at=value.reviewed_at,
                    reviewed_by_identity_id=value.reviewed_by_identity_id,
                    reason_code=value.reason_code,
                )
                .returning(merchant_verifications)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MerchantConflict("merchant_verification_not_reviewable")
        self.event(
            value.merchant_id,
            "merchant.verification.reviewed",
            {"kind": value.kind.value, "state": value.state.value},
            value.reviewed_at or value.submitted_at,
        )
        return _model(VerificationEvidence, row)

    def set_profile_state(
        self, merchant_id: UUID, state: str, *, expected_version: int, at: datetime
    ) -> MerchantProfile:
        row = (
            self._connection.execute(
                update(merchant_profiles)
                .where(
                    merchant_profiles.c.merchant_id == merchant_id,
                    merchant_profiles.c.version == expected_version,
                )
                .values(state=state, updated_at=at, version=expected_version + 1)
                .returning(merchant_profiles)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MerchantConflict("merchant_version_conflict")
        return _model(MerchantProfile, row)

    def get_program(
        self, program_id: UUID, *, lock: bool = False
    ) -> PartnerProgram | None:
        query = select(merchant_partner_programs).where(
            merchant_partner_programs.c.program_id == program_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _model(PartnerProgram, row)

    def create_program(self, value: PartnerProgram) -> PartnerProgram:
        self._connection.execute(
            insert(merchant_partner_programs).values(**value.model_dump(mode="json"))
        )
        return value

    def enrollment_count(self, program_id: UUID) -> int:
        return int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_program_enrollments)
                .where(merchant_program_enrollments.c.program_id == program_id)
            ).scalar_one()
        )

    def enroll(self, value: ProgramEnrollment) -> ProgramEnrollment:
        row = (
            self._connection.execute(
                pg_insert(merchant_program_enrollments)
                .values(**value.model_dump(mode="json"))
                .on_conflict_do_nothing()
                .returning(merchant_program_enrollments)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            existing = (
                self._connection.execute(
                    select(merchant_program_enrollments).where(
                        merchant_program_enrollments.c.program_id == value.program_id,
                        merchant_program_enrollments.c.merchant_id == value.merchant_id,
                    )
                )
                .mappings()
                .one()
            )
            return _model(ProgramEnrollment, existing)
        self.event(
            value.merchant_id,
            "merchant.program.enrolled",
            {"program_id": str(value.program_id)},
            value.enrolled_at,
        )
        return _model(ProgramEnrollment, row)

    def badges(self, merchant_id: UUID) -> tuple[str, ...]:
        rows = self._connection.execute(
            select(merchant_partner_programs.c.badge_label)
            .select_from(merchant_program_enrollments.join(merchant_partner_programs))
            .where(merchant_program_enrollments.c.merchant_id == merchant_id)
            .order_by(merchant_partner_programs.c.badge_label)
        ).scalars()
        return tuple(rows)

    def create_item(self, value: CatalogueItem) -> CatalogueItem:
        self._connection.execute(
            insert(merchant_catalogue_items).values(**value.model_dump(mode="json"))
        )
        self.event(
            value.merchant_id,
            "merchant.catalogue.item.created",
            {"item_id": str(value.item_id), "state": value.state.value},
            value.created_at,
        )
        return value

    def get_item(self, item_id: UUID, *, lock: bool = False) -> CatalogueItem | None:
        query = select(merchant_catalogue_items).where(
            merchant_catalogue_items.c.item_id == item_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _model(CatalogueItem, row)

    def set_item_state(
        self, item_id: UUID, state: str, *, expected_version: int, at: datetime
    ) -> CatalogueItem:
        row = (
            self._connection.execute(
                update(merchant_catalogue_items)
                .where(
                    merchant_catalogue_items.c.item_id == item_id,
                    merchant_catalogue_items.c.version == expected_version,
                )
                .values(state=state, updated_at=at, version=expected_version + 1)
                .returning(merchant_catalogue_items)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MerchantConflict("merchant_catalogue_version_conflict")
        return _model(CatalogueItem, row)

    def catalogue_counts(self, merchant_id: UUID) -> tuple[int, int]:
        total = int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_catalogue_items)
                .where(merchant_catalogue_items.c.merchant_id == merchant_id)
            ).scalar_one()
        )
        ready = int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_catalogue_items)
                .where(
                    merchant_catalogue_items.c.merchant_id == merchant_id,
                    merchant_catalogue_items.c.state == "ready",
                )
            ).scalar_one()
        )
        return total, ready

    def record_assistance(
        self,
        merchant_id: UUID,
        representative_id: UUID,
        activity: str,
        verified: bool,
        at: datetime,
    ) -> None:
        self._connection.execute(
            pg_insert(merchant_assistance)
            .values(
                assistance_id=uuid4(),
                merchant_id=merchant_id,
                representative_identity_id=representative_id,
                activity_code=activity,
                verified_onboarding=verified,
                recorded_at=at,
            )
            .on_conflict_do_nothing()
        )

    def representative_verified_count(self, representative_id: UUID) -> int:
        return int(
            self._connection.execute(
                select(func.count())
                .select_from(merchant_assistance)
                .where(
                    merchant_assistance.c.representative_identity_id
                    == representative_id,
                    merchant_assistance.c.verified_onboarding.is_(True),
                )
            ).scalar_one()
        )

    def event(
        self, merchant_id: UUID, event_type: str, payload: dict[str, Any], at: datetime
    ) -> None:
        self._connection.execute(
            insert(merchant_outbox).values(
                message_id=uuid4(),
                merchant_id=merchant_id,
                event_type=event_type,
                safe_payload=payload,
                occurred_at=at,
                attempt_count=0,
            )
        )
