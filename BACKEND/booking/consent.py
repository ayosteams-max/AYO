from datetime import datetime

from BACKEND.booking.models import BookingConflict, BookingConsentMetadata


class ImmutableBookingConsentRegistry:
    def __init__(self, policies: tuple[BookingConsentMetadata, ...]) -> None:
        versions = tuple(policy.required_version for policy in policies)
        if len(versions) != len(set(versions)):
            raise BookingConflict("consent_policy_unavailable")
        self._policies = policies

    def required_policy(self, *, at: datetime) -> BookingConsentMetadata:
        active = tuple(
            policy
            for policy in self._policies
            if policy.effective_from <= at
            and (policy.effective_until is None or at < policy.effective_until)
        )
        if len(active) != 1:
            raise BookingConflict("consent_policy_unavailable")
        return active[0]

    def policy_for_version(self, version: str) -> BookingConsentMetadata | None:
        matches = tuple(
            policy for policy in self._policies if policy.required_version == version
        )
        return matches[0] if len(matches) == 1 else None
