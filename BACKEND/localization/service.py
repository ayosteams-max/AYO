from datetime import datetime
from uuid import uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.localization.models import LanguagePreference
from BACKEND.persistence.composition import PostgresRepositoryComposition


class LocalizationAccessDenied(RuntimeError):
    pass


class LocalizationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def set_own_preference(
        self,
        *,
        subject: AuthorizationSubject,
        preferred_language: str,
        device_language: str | None,
        fallback_chain: tuple[str, ...],
        expected_version: int | None,
        at: datetime,
    ) -> LanguagePreference:
        with self._composition.unit_of_work() as unit:
            current = unit.localization.get_preference(subject.identity_id)
            if (current is None) != (expected_version is None):
                raise ValueError("Stale language-preference version")
            version = 1 if current is None else current.version + 1
            value = LanguagePreference(
                preference_id=uuid4() if current is None else current.preference_id,
                identity_id=subject.identity_id,
                preferred_language=preferred_language,
                device_language=device_language,
                fallback_chain=fallback_chain,
                version=version,
                updated_at=at,
            )
            return unit.localization.save_preference(
                value, expected_version=expected_version
            )

    def get_own_preference(
        self, *, subject: AuthorizationSubject
    ) -> LanguagePreference | None:
        with self._composition.unit_of_work() as unit:
            return unit.localization.get_preference(subject.identity_id)
