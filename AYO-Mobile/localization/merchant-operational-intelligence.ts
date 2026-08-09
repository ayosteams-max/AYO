import type { MerchantOperationalIntelligenceResult } from '@/domain/merchant-operational-intelligence';
import type { SupportedLocale } from '@/localization/authentication';

type Reason = MerchantOperationalIntelligenceResult['reason'];
type LanguageKey = 'noAction' | 'authorityChanged' | 'unsupported' | 'acknowledge' | 'acknowledging' |
  'acknowledged' | 'checkStatus' | 'checkingStatus' | 'retrySame' | 'retry' | 'uncertain' |
  'retryUnavailable' | 'rejected';
type Recommendation = MerchantOperationalIntelligenceResult['recommendation'];

type Mapping = Readonly<{
  recommendation: Recommendation;
  userActionAvailable: boolean;
  languageKey: LanguageKey;
  visible: boolean;
  tone: 'neutral' | 'informative' | 'positive' | 'caution';
}>;

const mappings = Object.freeze({
  NO_CURRENT_ACK_ACTION: { recommendation: 'no_action', userActionAvailable: false, languageKey: 'noAction', visible: false, tone: 'neutral' },
  ACK_AUTHORITY_CHANGED: { recommendation: 'no_action', userActionAvailable: false, languageKey: 'authorityChanged', visible: false, tone: 'neutral' },
  UNSUPPORTED_ACK_STATE: { recommendation: 'no_action', userActionAvailable: false, languageKey: 'unsupported', visible: false, tone: 'neutral' },
  ACK_ALLOWED_BY_CAPABILITY: { recommendation: 'acknowledge_arrival', userActionAvailable: true, languageKey: 'acknowledge', visible: true, tone: 'informative' },
  ACK_IN_PROGRESS: { recommendation: 'acknowledging_arrival', userActionAvailable: false, languageKey: 'acknowledging', visible: true, tone: 'informative' },
  ACK_CONFIRMED: { recommendation: 'arrival_acknowledged', userActionAvailable: false, languageKey: 'acknowledged', visible: true, tone: 'positive' },
  ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE: { recommendation: 'check_acknowledgement_status', userActionAvailable: true, languageKey: 'checkStatus', visible: true, tone: 'caution' },
  ACK_RECONCILIATION_IN_PROGRESS: { recommendation: 'checking_acknowledgement_status', userActionAvailable: false, languageKey: 'checkingStatus', visible: true, tone: 'informative' },
  ACK_SAME_ATTEMPT_RETRY_AVAILABLE: { recommendation: 'retry_same_acknowledgement', userActionAvailable: true, languageKey: 'retrySame', visible: true, tone: 'caution' },
  ACK_RETRY_ALLOWED_BY_CAPABILITY: { recommendation: 'retry_acknowledgement', userActionAvailable: true, languageKey: 'retry', visible: true, tone: 'caution' },
  ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION: { recommendation: 'acknowledgement_issue', userActionAvailable: false, languageKey: 'uncertain', visible: true, tone: 'caution' },
  ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED: { recommendation: 'acknowledgement_issue', userActionAvailable: false, languageKey: 'retryUnavailable', visible: true, tone: 'caution' },
  ACK_REJECTED_NO_CURRENT_ACTION: { recommendation: 'acknowledgement_issue', userActionAvailable: false, languageKey: 'rejected', visible: true, tone: 'caution' },
} as const satisfies Readonly<Record<Reason, Mapping>>);

type CopyEntry = Readonly<{ headline: string; body: string; actionLabel?: string }>;
type Copy = Readonly<Record<LanguageKey, CopyEntry>>;

const english: Copy = Object.freeze({
  noAction: { headline: 'No action needed', body: 'There is no arrival acknowledgement action available right now.' },
  authorityChanged: { headline: 'Status changed', body: 'This arrival acknowledgement action is no longer available.' },
  unsupported: { headline: 'Status unavailable', body: 'AYO cannot safely suggest an arrival acknowledgement action right now.' },
  acknowledge: { headline: 'Courier has arrived', body: 'You can acknowledge the courier’s arrival now.', actionLabel: 'Acknowledge arrival' },
  acknowledging: { headline: 'Acknowledging arrival', body: 'AYO is confirming your acknowledgement.' },
  acknowledged: { headline: 'Arrival acknowledged', body: 'The courier’s arrival has been confirmed.' },
  checkStatus: { headline: 'Confirmation not clear yet', body: 'AYO could not confirm the result. You can check the current status.', actionLabel: 'Check status' },
  checkingStatus: { headline: 'Checking status', body: 'AYO is checking the latest acknowledgement status.' },
  retrySame: { headline: 'Try acknowledgement again', body: 'You can retry the same acknowledgement safely.', actionLabel: 'Try again' },
  retry: { headline: 'Try again', body: 'The previous acknowledgement did not complete. You can try again.', actionLabel: 'Try again' },
  uncertain: { headline: 'Confirmation not clear yet', body: 'AYO could not confirm the result. No action is available right now.' },
  retryUnavailable: { headline: 'Action not available right now', body: 'The acknowledgement cannot be retried safely right now.' },
  rejected: { headline: 'Action not available right now', body: 'The arrival acknowledgement did not complete, and no action is available right now.' },
});

// NEEDS_NATIVE_AMHARIC_REVIEW: operational acknowledgement guidance requires native review before production.
const amharic: Copy = Object.freeze({
  noAction: { headline: 'አሁን የሚያስፈልግ እርምጃ የለም', body: 'አሁን የመድረስ ማረጋገጫ እርምጃ አይገኝም።' },
  authorityChanged: { headline: 'ሁኔታው ተቀይሯል', body: 'ይህ የመድረስ ማረጋገጫ እርምጃ ከእንግዲህ አይገኝም።' },
  unsupported: { headline: 'ሁኔታው አይገኝም', body: 'AYO አሁን የመድረስ ማረጋገጫ እርምጃን በደህና ሊጠቁም አይችልም።' },
  acknowledge: { headline: 'መልእክተኛው ደርሷል', body: 'የመልእክተኛውን መድረስ አሁን ማረጋገጥ ይችላሉ።', actionLabel: 'መድረሱን አረጋግጥ' },
  acknowledging: { headline: 'መድረሱ እየተረጋገጠ ነው', body: 'AYO ማረጋገጫዎን እያረጋገጠ ነው።' },
  acknowledged: { headline: 'መድረሱ ተረጋግጧል', body: 'የመልእክተኛው መድረስ ተረጋግጧል።' },
  checkStatus: { headline: 'ማረጋገጫው ገና ግልጽ አይደለም', body: 'AYO ውጤቱን ማረጋገጥ አልቻለም። የአሁኑን ሁኔታ ማየት ይችላሉ።', actionLabel: 'ሁኔታውን ይመልከቱ' },
  checkingStatus: { headline: 'ሁኔታው እየታየ ነው', body: 'AYO የቅርብ ጊዜውን የማረጋገጫ ሁኔታ እያየ ነው።' },
  retrySame: { headline: 'ማረጋገጫውን እንደገና ይሞክሩ', body: 'ይኸውን ማረጋገጫ በደህና እንደገና መሞከር ይችላሉ።', actionLabel: 'እንደገና ሞክር' },
  retry: { headline: 'እንደገና ይሞክሩ', body: 'የቀድሞው ማረጋገጫ አልተጠናቀቀም። እንደገና መሞከር ይችላሉ።', actionLabel: 'እንደገና ሞክር' },
  uncertain: { headline: 'ማረጋገጫው ገና ግልጽ አይደለም', body: 'AYO ውጤቱን ማረጋገጥ አልቻለም። አሁን የሚገኝ እርምጃ የለም።' },
  retryUnavailable: { headline: 'እርምጃው አሁን አይገኝም', body: 'ማረጋገጫውን አሁን በደህና እንደገና መሞከር አይቻልም።' },
  rejected: { headline: 'እርምጃው አሁን አይገኝም', body: 'የመድረስ ማረጋገጫው አልተጠናቀቀም፣ እና አሁን የሚገኝ እርምጃ የለም።' },
});

const copy = Object.freeze({ en: english, am: amharic });
const neutral = Object.freeze({
  headline: english.unsupported.headline,
  body: english.unsupported.body,
  tone: 'neutral' as const,
  reason: 'UNSUPPORTED_ACK_STATE' as const,
  userActionAvailable: false as const,
  visible: false as const,
});

export type MerchantOperationalIntelligenceLanguage = Readonly<{
  headline: string;
  body: string;
  actionLabel?: string;
  tone: Mapping['tone'];
  reason: Reason;
  userActionAvailable: boolean;
  visible: boolean;
}>;

/** Converts locked Phase 1 semantics into bounded language; it owns no authority or command. */
export function explainMerchantOperationalIntelligence(
  intelligence: MerchantOperationalIntelligenceResult,
  locale: SupportedLocale,
): MerchantOperationalIntelligenceLanguage {
  if (!intelligence || typeof intelligence !== 'object') return neutral;
  const mapping = mappings[(intelligence as MerchantOperationalIntelligenceResult).reason];
  if (!mapping || mapping.recommendation !== intelligence.recommendation ||
      mapping.userActionAvailable !== intelligence.userActionAvailable) return neutral;
  const words = (copy[locale] ?? copy.en)[mapping.languageKey];
  return Object.freeze({ ...words, tone: mapping.tone, reason: intelligence.reason,
    userActionAvailable: intelligence.userActionAvailable, visible: mapping.visible });
}
