from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.identity.compatibility_models import (
    AccountLifecycle,
    CanonicalSubject,
    IdentityAccount,
    LegacyIdentityMapping,
    LegacySemantic,
    MappingState,
    SubjectKind,
)
from BACKEND.persistence.errors import OptimisticConcurrencyError, PersistenceError
from BACKEND.persistence.tables import (
    canonical_subjects,
    identities,
    identity_accounts,
    legacy_identity_mappings,
)


class LegacyMeaningAmbiguous(PersistenceError):
    """A legacy reference has no approved authorization-safe account meaning."""


class CompatibilityConflict(PersistenceError):
    """A compatibility identity or one-to-one mapping already conflicts."""


def _subject(row: Mapping[Any, Any]) -> CanonicalSubject:
    return CanonicalSubject.model_validate(dict(row))


def _account(row: Mapping[Any, Any]) -> IdentityAccount:
    return IdentityAccount.model_validate(dict(row))


def _mapping(row: Mapping[Any, Any]) -> LegacyIdentityMapping:
    return LegacyIdentityMapping.model_validate(dict(row))


class PostgresIdentityCompatibilityRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def map_legacy_subject(
        self,
        *,
        legacy_identity_id: UUID,
        semantic: LegacySemantic,
        provenance: str,
        at: datetime,
    ) -> tuple[CanonicalSubject, LegacyIdentityMapping, bool]:
        legacy = (
            self._connection.execute(
                select(identities.c.identity_type)
                .where(identities.c.identity_id == legacy_identity_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if legacy is None:
            raise CompatibilityConflict("Legacy identity does not exist.")
        existing = self.get_mapping(legacy_identity_id)
        if existing is not None:
            if existing.semantic is not semantic:
                raise CompatibilityConflict(
                    "Legacy identity already has a different semantic classification."
                )
            subject = self.get_subject(existing.subject_id)
            if subject is None:
                raise CompatibilityConflict("Mapped canonical subject is missing.")
            return subject, existing, False

        legacy_type = str(legacy["identity_type"])
        kind = {
            "service": SubjectKind.SERVICE,
            "rider": SubjectKind.HUMAN,
            "driver": SubjectKind.HUMAN,
            "staff": SubjectKind.HUMAN,
            "administrator": SubjectKind.HUMAN,
        }.get(legacy_type, SubjectKind.OTHER)
        subject = CanonicalSubject(subject_kind=kind, created_at=at)
        mapping = LegacyIdentityMapping(
            legacy_identity_id=legacy_identity_id,
            subject_id=subject.subject_id,
            semantic=semantic,
            mapping_state=(
                MappingState.AMBIGUOUS
                if semantic is LegacySemantic.AMBIGUOUS
                else MappingState.SUBJECT_MAPPED
            ),
            provenance=provenance,
            created_at=at,
            updated_at=at,
        )
        try:
            self._connection.execute(
                insert(canonical_subjects).values(**subject.model_dump(mode="python"))
            )
            self._connection.execute(
                insert(legacy_identity_mappings).values(
                    **mapping.model_dump(mode="python")
                )
            )
        except IntegrityError as error:
            raise CompatibilityConflict(
                "Canonical subject or legacy mapping already exists."
            ) from error
        return subject, mapping, True

    def create_account(
        self,
        *,
        legacy_identity_id: UUID,
        at: datetime,
        expected_mapping_version: int,
    ) -> tuple[IdentityAccount, LegacyIdentityMapping, bool]:
        mapping_row = (
            self._connection.execute(
                select(legacy_identity_mappings)
                .where(
                    legacy_identity_mappings.c.legacy_identity_id == legacy_identity_id
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if mapping_row is None:
            raise LegacyMeaningAmbiguous(
                "Legacy identity has no compatibility mapping."
            )
        mapping = _mapping(mapping_row)
        if mapping.semantic not in {
            LegacySemantic.ACCOUNT,
            LegacySemantic.AUTHENTICATION_ACTOR,
            LegacySemantic.AUTHORIZATION_PRINCIPAL,
        }:
            raise LegacyMeaningAmbiguous(
                "Legacy meaning is not approved for account creation."
            )
        if mapping.account_id is not None:
            account = self.get_account(mapping.account_id)
            if account is None:
                raise CompatibilityConflict("Mapped account is missing.")
            return account, mapping, False
        if mapping.version != expected_mapping_version:
            raise OptimisticConcurrencyError("Compatibility mapping changed.")

        account = IdentityAccount(
            subject_id=mapping.subject_id,
            state=AccountLifecycle.PENDING_ACTIVATION,
            created_at=at,
            updated_at=at,
        )
        self._connection.execute(
            insert(identity_accounts).values(**account.model_dump(mode="python"))
        )
        updated = (
            self._connection.execute(
                update(legacy_identity_mappings)
                .where(
                    legacy_identity_mappings.c.mapping_id == mapping.mapping_id,
                    legacy_identity_mappings.c.version == expected_mapping_version,
                    legacy_identity_mappings.c.account_id.is_(None),
                )
                .values(
                    account_id=account.account_id,
                    mapping_state=MappingState.ACCOUNT_MAPPED.value,
                    updated_at=at,
                    version=legacy_identity_mappings.c.version + 1,
                )
                .returning(legacy_identity_mappings)
            )
            .mappings()
            .one_or_none()
        )
        if updated is None:
            raise OptimisticConcurrencyError("Compatibility mapping changed.")
        return account, _mapping(updated), True

    def transition_account(
        self,
        account: IdentityAccount,
        *,
        target: AccountLifecycle,
        at: datetime,
        expected_version: int,
    ) -> IdentityAccount:
        transitioned = account.transition(target, at=at)
        row = (
            self._connection.execute(
                update(identity_accounts)
                .where(
                    identity_accounts.c.account_id == account.account_id,
                    identity_accounts.c.version == expected_version,
                )
                .values(
                    state=transitioned.state.value,
                    updated_at=transitioned.updated_at,
                    version=identity_accounts.c.version + 1,
                )
                .returning(identity_accounts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Canonical account changed.")
        return _account(row)

    def resolve_authorization_account(
        self, legacy_identity_id: UUID
    ) -> IdentityAccount:
        row = (
            self._connection.execute(
                select(identity_accounts)
                .select_from(
                    legacy_identity_mappings.join(
                        identity_accounts,
                        identity_accounts.c.account_id
                        == legacy_identity_mappings.c.account_id,
                    )
                )
                .where(
                    legacy_identity_mappings.c.legacy_identity_id == legacy_identity_id,
                    legacy_identity_mappings.c.semantic
                    == LegacySemantic.AUTHORIZATION_PRINCIPAL.value,
                    legacy_identity_mappings.c.mapping_state
                    == MappingState.ACCOUNT_MAPPED.value,
                    identity_accounts.c.state == "active",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LegacyMeaningAmbiguous(
                "Authorization-sensitive legacy meaning is unresolved."
            )
        return _account(row)

    def get_subject(self, subject_id: UUID) -> CanonicalSubject | None:
        row = (
            self._connection.execute(
                select(canonical_subjects).where(
                    canonical_subjects.c.subject_id == subject_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _subject(row)

    def get_account(self, account_id: UUID) -> IdentityAccount | None:
        row = (
            self._connection.execute(
                select(identity_accounts).where(
                    identity_accounts.c.account_id == account_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _account(row)

    def get_mapping(self, legacy_identity_id: UUID) -> LegacyIdentityMapping | None:
        row = (
            self._connection.execute(
                select(legacy_identity_mappings).where(
                    legacy_identity_mappings.c.legacy_identity_id == legacy_identity_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _mapping(row)
