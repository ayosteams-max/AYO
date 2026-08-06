from dataclasses import dataclass
from datetime import datetime
from typing import Any

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantProfile, MerchantState
from BACKEND.mobile_context.models import (
    CourierMobileContext,
    MerchantContextAvailability,
    MerchantMobileContext,
    MobileContextResponse,
    PersonalMobileContext,
)


class MobileContextUnavailable(Exception):
    """The bounded public projection cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class MobileContextFeatures:
    personal_enabled: bool
    merchant_enabled: bool
    courier_dispatch_enabled: bool
    courier_pickup_enabled: bool


class MobileContextApplication:
    MAX_MERCHANT_CONTEXTS = 50

    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def read(
        self,
        subject: AuthorizationSubject,
        *,
        features: MobileContextFeatures,
        at: datetime,
    ) -> MobileContextResponse:
        personal = (
            PersonalMobileContext()
            if features.personal_enabled and subject.identity_type is IdentityType.RIDER
            else None
        )
        merchants: tuple[MerchantMobileContext, ...] = ()
        courier: CourierMobileContext | None = None

        with self._composition.unit_of_work() as unit:
            if features.merchant_enabled and unit.authorization.has_permission(
                subject.identity_id, "merchant.dashboard.read_own", at=at
            ):
                owned = unit.merchants.list_owned(
                    subject.identity_id, limit=self.MAX_MERCHANT_CONTEXTS + 1
                )
                if len(owned) > self.MAX_MERCHANT_CONTEXTS:
                    raise MobileContextUnavailable("merchant_context_limit_exceeded")
                merchants = tuple(
                    self._merchant_context(item)
                    for item in sorted(
                        owned,
                        key=lambda item: (
                            item.display_name.casefold(),
                            str(item.merchant_id),
                        ),
                    )
                )

            if (
                features.courier_dispatch_enabled
                and features.courier_pickup_enabled
                and unit.authorization.has_permission(
                    subject.identity_id, "courier_pickup.manage_assigned", at=at
                )
            ):
                current = unit.courier_pickup.current_for_courier(subject.identity_id)
                if len(current) == 1:
                    courier = CourierMobileContext(pickup_id=current[0].pickup_id)

        return MobileContextResponse(
            personal=personal,
            merchants=merchants,
            courier=courier,
        )

    @staticmethod
    def _merchant_context(profile: MerchantProfile) -> MerchantMobileContext:
        availability = {
            MerchantState.DRAFT: MerchantContextAvailability.PENDING,
            MerchantState.VERIFICATION_PENDING: MerchantContextAvailability.PENDING,
            MerchantState.APPROVED: MerchantContextAvailability.AVAILABLE,
            MerchantState.SUSPENDED: MerchantContextAvailability.SUSPENDED,
        }.get(profile.state)
        if availability is None:
            raise MobileContextUnavailable("unsupported_merchant_state")
        return MerchantMobileContext(
            merchant_id=profile.merchant_id,
            display_name=profile.display_name,
            availability=availability,
        )
