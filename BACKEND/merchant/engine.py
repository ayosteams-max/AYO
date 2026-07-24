from datetime import datetime

from BACKEND.merchant.models import (
    MerchantProfile,
    PartnerProgram,
    VerificationKind,
    VerificationState,
)


class MerchantConflict(ValueError):
    pass


def verification_requirements(capability_code: str) -> tuple[VerificationKind, ...]:
    base = (
        VerificationKind.IDENTITY,
        VerificationKind.BUSINESS_LICENCE,
        VerificationKind.TAX_REGISTRATION,
        VerificationKind.BANK_OR_PAYMENT,
    )
    return (
        (*base, VerificationKind.FOOD_LICENCE)
        if capability_code == "merchant.food"
        else base
    )


def assert_program_open(
    program: PartnerProgram, *, enrollment_count: int, at: datetime
) -> None:
    if not program.active or not (program.opens_at <= at < program.closes_at):
        raise MerchantConflict("partner_program_closed")
    if (
        program.participant_limit is not None
        and enrollment_count >= program.participant_limit
    ):
        raise MerchantConflict("partner_program_full")


def readiness(
    merchant: MerchantProfile,
    verification_states: tuple[VerificationState, ...],
    *,
    catalogue_total: int,
    catalogue_ready: int,
) -> tuple[int, int, int, bool]:
    onboarding = 100 if merchant.display_name and merchant.legal_name else 0
    required = len(verification_states)
    approved = sum(state is VerificationState.APPROVED for state in verification_states)
    verification = 100 if required == 0 else approved * 100 // required
    catalogue = 0 if catalogue_total == 0 else catalogue_ready * 100 // catalogue_total
    return (
        onboarding,
        verification,
        catalogue,
        onboarding == verification == catalogue == 100,
    )
