from dataclasses import dataclass

from BACKEND.merchant_intelligence.generative import Locale, Reason


@dataclass(frozen=True, slots=True)
class CanonicalMerchantIntelligenceLanguage:
    headline: str
    body: str
    action_label: str | None = None


_ENGLISH: dict[Reason, CanonicalMerchantIntelligenceLanguage] = {
    "ACK_ALLOWED_BY_CAPABILITY": CanonicalMerchantIntelligenceLanguage(
        "Courier has arrived",
        "You can acknowledge the courier’s arrival now.",
        "Acknowledge arrival",
    ),
    "ACK_IN_PROGRESS": CanonicalMerchantIntelligenceLanguage(
        "Acknowledging arrival", "AYO is confirming your acknowledgement."
    ),
    "ACK_CONFIRMED": CanonicalMerchantIntelligenceLanguage(
        "Arrival acknowledged", "The courier’s arrival has been confirmed."
    ),
    "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE": CanonicalMerchantIntelligenceLanguage(
        "Confirmation not clear yet",
        "AYO could not confirm the result. You can check the current status.",
        "Check status",
    ),
    "ACK_RECONCILIATION_IN_PROGRESS": CanonicalMerchantIntelligenceLanguage(
        "Checking status", "AYO is checking the latest acknowledgement status."
    ),
    "ACK_SAME_ATTEMPT_RETRY_AVAILABLE": CanonicalMerchantIntelligenceLanguage(
        "Try acknowledgement again",
        "You can retry the same acknowledgement safely.",
        "Try again",
    ),
    "ACK_RETRY_ALLOWED_BY_CAPABILITY": CanonicalMerchantIntelligenceLanguage(
        "Try again",
        "The previous acknowledgement did not complete. You can try again.",
        "Try again",
    ),
    "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION": CanonicalMerchantIntelligenceLanguage(
        "Confirmation not clear yet",
        "AYO could not confirm the result. No action is available right now.",
    ),
    "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED": CanonicalMerchantIntelligenceLanguage(
        "Action not available right now",
        "The acknowledgement cannot be retried safely right now.",
    ),
    "ACK_REJECTED_NO_CURRENT_ACTION": CanonicalMerchantIntelligenceLanguage(
        "Action not available right now",
        "The arrival acknowledgement did not complete, and no action is available right now.",
    ),
}

_AMHARIC: dict[Reason, CanonicalMerchantIntelligenceLanguage] = {
    "ACK_ALLOWED_BY_CAPABILITY": CanonicalMerchantIntelligenceLanguage(
        "መልእክተኛው ደርሷል", "የመልእክተኛውን መድረስ አሁን ማረጋገጥ ይችላሉ።", "መድረሱን አረጋግጥ"
    ),
    "ACK_IN_PROGRESS": CanonicalMerchantIntelligenceLanguage(
        "መድረሱ እየተረጋገጠ ነው", "AYO ማረጋገጫዎን እያረጋገጠ ነው።"
    ),
    "ACK_CONFIRMED": CanonicalMerchantIntelligenceLanguage(
        "መድረሱ ተረጋግጧል", "የመልእክተኛው መድረስ ተረጋግጧል።"
    ),
    "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE": CanonicalMerchantIntelligenceLanguage(
        "ማረጋገጫው ገና ግልጽ አይደለም",
        "AYO ውጤቱን ማረጋገጥ አልቻለም። የአሁኑን ሁኔታ ማየት ይችላሉ።",
        "ሁኔታውን ይመልከቱ",
    ),
    "ACK_RECONCILIATION_IN_PROGRESS": CanonicalMerchantIntelligenceLanguage(
        "ሁኔታው እየታየ ነው", "AYO የቅርብ ጊዜውን የማረጋገጫ ሁኔታ እያየ ነው።"
    ),
    "ACK_SAME_ATTEMPT_RETRY_AVAILABLE": CanonicalMerchantIntelligenceLanguage(
        "ማረጋገጫውን እንደገና ይሞክሩ",
        "ይኸውን ማረጋገጫ በደህና እንደገና መሞከር ይችላሉ።",
        "እንደገና ሞክር",
    ),
    "ACK_RETRY_ALLOWED_BY_CAPABILITY": CanonicalMerchantIntelligenceLanguage(
        "እንደገና ይሞክሩ",
        "የቀድሞው ማረጋገጫ አልተጠናቀቀም። እንደገና መሞከር ይችላሉ።",
        "እንደገና ሞክር",
    ),
    "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION": CanonicalMerchantIntelligenceLanguage(
        "ማረጋገጫው ገና ግልጽ አይደለም",
        "AYO ውጤቱን ማረጋገጥ አልቻለም። አሁን የሚገኝ እርምጃ የለም።",
    ),
    "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED": CanonicalMerchantIntelligenceLanguage(
        "እርምጃው አሁን አይገኝም", "ማረጋገጫውን አሁን በደህና እንደገና መሞከር አይቻልም።"
    ),
    "ACK_REJECTED_NO_CURRENT_ACTION": CanonicalMerchantIntelligenceLanguage(
        "እርምጃው አሁን አይገኝም",
        "የመድረስ ማረጋገጫው አልተጠናቀቀም፣ እና አሁን የሚገኝ እርምጃ የለም።",
    ),
}

_LANGUAGE = {"en": _ENGLISH, "am": _AMHARIC}


def canonical_merchant_intelligence_language(
    locale: Locale, reason: Reason
) -> CanonicalMerchantIntelligenceLanguage:
    return _LANGUAGE[locale][reason]
