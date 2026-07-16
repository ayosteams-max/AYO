from uuid import UUID

from sqlalchemy import Connection, insert, select, update

from BACKEND.localization.models import LanguagePackManifest, LanguagePreference
from BACKEND.persistence.tables import (
    localization_pack_manifests,
    localization_preferences,
)


class PostgresLocalizationRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_preference(self, identity_id: UUID) -> LanguagePreference | None:
        row = (
            self._connection.execute(
                select(localization_preferences).where(
                    localization_preferences.c.identity_id == identity_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else LanguagePreference.model_validate(dict(row))

    def save_preference(
        self, value: LanguagePreference, *, expected_version: int | None
    ) -> LanguagePreference:
        values = value.model_dump()
        values["fallback_chain"] = list(value.fallback_chain)
        if expected_version is None:
            self._connection.execute(insert(localization_preferences).values(**values))
            return value
        row = (
            self._connection.execute(
                update(localization_preferences)
                .where(
                    localization_preferences.c.identity_id == value.identity_id,
                    localization_preferences.c.version == expected_version,
                )
                .values(
                    preferred_language=value.preferred_language,
                    device_language=value.device_language,
                    fallback_chain=list(value.fallback_chain),
                    version=value.version,
                    updated_at=value.updated_at,
                )
                .returning(localization_preferences)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("Stale language-preference version")
        return LanguagePreference.model_validate(dict(row))

    def add_manifest(self, value: LanguagePackManifest) -> None:
        self._connection.execute(
            insert(localization_pack_manifests).values(**value.model_dump())
        )

    def manifest(self, tag: str) -> LanguagePackManifest | None:
        row = (
            self._connection.execute(
                select(localization_pack_manifests)
                .where(localization_pack_manifests.c.language_tag == tag)
                .order_by(localization_pack_manifests.c.pack_version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else LanguagePackManifest.model_validate(dict(row))
