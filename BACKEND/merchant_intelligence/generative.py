import asyncio
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from BACKEND.authorization.contracts import AuthorizationSubject

PromptVersion = Literal["merchant_ack_explanation_v1"]
Locale = Literal["en", "am"]
Tone = Literal["neutral", "informative", "positive", "caution"]
Recommendation = Literal[
    "acknowledge_arrival",
    "acknowledging_arrival",
    "arrival_acknowledged",
    "check_acknowledgement_status",
    "checking_acknowledgement_status",
    "retry_same_acknowledgement",
    "retry_acknowledgement",
    "acknowledgement_issue",
]
Reason = Literal[
    "ACK_ALLOWED_BY_CAPABILITY",
    "ACK_IN_PROGRESS",
    "ACK_CONFIRMED",
    "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE",
    "ACK_RECONCILIATION_IN_PROGRESS",
    "ACK_SAME_ATTEMPT_RETRY_AVAILABLE",
    "ACK_RETRY_ALLOWED_BY_CAPABILITY",
    "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION",
    "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED",
    "ACK_REJECTED_NO_CURRENT_ACTION",
]

_SEMANTICS: dict[str, tuple[str, bool, str]] = {
    "ACK_ALLOWED_BY_CAPABILITY": ("acknowledge_arrival", True, "informative"),
    "ACK_IN_PROGRESS": ("acknowledging_arrival", False, "informative"),
    "ACK_CONFIRMED": ("arrival_acknowledged", False, "positive"),
    "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE": (
        "check_acknowledgement_status",
        True,
        "caution",
    ),
    "ACK_RECONCILIATION_IN_PROGRESS": (
        "checking_acknowledgement_status",
        False,
        "informative",
    ),
    "ACK_SAME_ATTEMPT_RETRY_AVAILABLE": ("retry_same_acknowledgement", True, "caution"),
    "ACK_RETRY_ALLOWED_BY_CAPABILITY": ("retry_acknowledgement", True, "caution"),
    "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION": (
        "acknowledgement_issue",
        False,
        "caution",
    ),
    "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED": (
        "acknowledgement_issue",
        False,
        "caution",
    ),
    "ACK_REJECTED_NO_CURRENT_ACTION": ("acknowledgement_issue", False, "caution"),
}


class MerchantGenerativeExplanationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: PromptVersion = Field(alias="promptVersion")
    locale: Locale
    recommendation: Recommendation
    reason: Reason
    deterministic_headline: str = Field(
        alias="deterministicHeadline", min_length=1, max_length=80
    )
    deterministic_body: str = Field(
        alias="deterministicBody", min_length=1, max_length=240
    )
    deterministic_action_label: str | None = Field(
        default=None, alias="deterministicActionLabel", min_length=1, max_length=64
    )
    user_action_available: bool = Field(alias="userActionAvailable")
    tone: Tone

    @model_validator(mode="after")
    def bounded_semantics(self) -> "MerchantGenerativeExplanationRequest":
        expected = _SEMANTICS[self.reason]
        if expected != (self.recommendation, self.user_action_available, self.tone):
            raise ValueError("incoherent merchant intelligence semantics")
        for value in (
            self.deterministic_headline,
            self.deterministic_body,
            self.deterministic_action_label,
        ):
            if value is not None and (
                value != value.strip()
                or any(
                    ord(character) < 32 or ord(character) == 127 for character in value
                )
            ):
                raise ValueError("deterministic text is not canonical")
        if self.user_action_available != (self.deterministic_action_label is not None):
            raise ValueError("action label does not match actionability")
        return self


class MerchantGenerativeExplanationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    locale: Locale
    headline: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def canonical_text(self) -> "MerchantGenerativeExplanationResponse":
        for value in (self.headline, self.body):
            if value != value.strip() or any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise ValueError("provider text is not canonical")
        return self


class MerchantGenerativeExplanationProvider(Protocol):
    async def generate_merchant_explanation(
        self, request: MerchantGenerativeExplanationRequest
    ) -> MerchantGenerativeExplanationResponse: ...


class MerchantGenerativeExplanationRateLimiter(Protocol):
    def allow(self, subject: AuthorizationSubject) -> bool: ...


class MerchantGenerativeExplanationUnavailable(Exception):
    pass


class MerchantGenerativeExplanationRateLimited(Exception):
    pass


class MerchantGenerativeExplanationApplication:
    """One-shot, text-only provider execution; it owns no command or model tools."""

    def __init__(
        self,
        provider: MerchantGenerativeExplanationProvider,
        rate_limiter: MerchantGenerativeExplanationRateLimiter,
        *,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not 0 < timeout_seconds <= 5:
            raise ValueError("Provider timeout is outside approved bounds")
        self._provider = provider
        self._rate_limiter = rate_limiter
        self._timeout_seconds = timeout_seconds

    async def explain(
        self,
        subject: AuthorizationSubject,
        request: MerchantGenerativeExplanationRequest,
    ) -> MerchantGenerativeExplanationResponse:
        if not self._rate_limiter.allow(subject):
            raise MerchantGenerativeExplanationRateLimited
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._provider.generate_merchant_explanation(request)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise MerchantGenerativeExplanationUnavailable from error
        try:
            validated = MerchantGenerativeExplanationResponse.model_validate(response)
        except Exception as error:
            raise MerchantGenerativeExplanationUnavailable from error
        if (
            validated.locale != request.locale
            or validated.headline != request.deterministic_headline
            or validated.body != request.deterministic_body
        ):
            raise MerchantGenerativeExplanationUnavailable
        return validated
