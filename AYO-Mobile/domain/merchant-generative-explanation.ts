import type { MerchantOperationalIntelligenceResult } from '@/domain/merchant-operational-intelligence';
import type { MerchantOperationalIntelligenceLanguage } from '@/localization/merchant-operational-intelligence';
import type { SupportedLocale } from '@/localization/authentication';

type Reason = MerchantOperationalIntelligenceResult['reason'];
type Recommendation = MerchantOperationalIntelligenceResult['recommendation'];

const maximumHeadlineLength = 80;
const maximumBodyLength = 240;

const supportedSemantics = Object.freeze({
  NO_CURRENT_ACK_ACTION: 'no_action',
  ACK_AUTHORITY_CHANGED: 'no_action',
  UNSUPPORTED_ACK_STATE: 'no_action',
  ACK_ALLOWED_BY_CAPABILITY: 'acknowledge_arrival',
  ACK_IN_PROGRESS: 'acknowledging_arrival',
  ACK_CONFIRMED: 'arrival_acknowledged',
  ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE: 'check_acknowledgement_status',
  ACK_RECONCILIATION_IN_PROGRESS: 'checking_acknowledgement_status',
  ACK_SAME_ATTEMPT_RETRY_AVAILABLE: 'retry_same_acknowledgement',
  ACK_RETRY_ALLOWED_BY_CAPABILITY: 'retry_acknowledgement',
  ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION: 'acknowledgement_issue',
  ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED: 'acknowledgement_issue',
  ACK_REJECTED_NO_CURRENT_ACTION: 'acknowledgement_issue',
} as const satisfies Readonly<Record<Reason, Recommendation>>);

export const merchantGenerativeExplanationPrompt = Object.freeze({
  version: 'merchant_ack_explanation_v1' as const,
  instructions: Object.freeze([
    'Explain only the trusted AYO intelligence supplied in the request.',
    'Do not invent facts, actions, authority, identifiers, or operational details.',
    'Do not change the recommendation or user action availability.',
    'Return only the strict locale, headline, and body schema.',
  ]),
});

export type MerchantGenerativeExplanationInput = Readonly<{
  locale: SupportedLocale;
  intelligence: MerchantOperationalIntelligenceResult;
  deterministic: MerchantOperationalIntelligenceLanguage;
}>;

export type MerchantGenerativeExplanationRequest = Readonly<{
  promptVersion: typeof merchantGenerativeExplanationPrompt.version;
  locale: SupportedLocale;
  recommendation: Recommendation;
  reason: Reason;
  deterministicHeadline: string;
  deterministicBody: string;
  deterministicActionLabel?: string;
  userActionAvailable: boolean;
  tone: MerchantOperationalIntelligenceLanguage['tone'];
}>;

export interface MerchantGenerativeExplanationProvider {
  generateExplanation(request: MerchantGenerativeExplanationRequest, signal?: AbortSignal): Promise<unknown>;
}

export type MerchantGenerativeExplanation = Readonly<MerchantOperationalIntelligenceLanguage & {
  source: 'deterministic_fallback' | 'generative_validated';
}>;

/**
 * A provider-neutral, presentation-only gateway. The initial admission policy accepts
 * generated text only when it exactly preserves the locked Phase 2 explanation.
 */
export class MerchantGenerativeExplanationGateway {
  private readonly provider?: MerchantGenerativeExplanationProvider;

  constructor(provider?: MerchantGenerativeExplanationProvider) {
    this.provider = provider;
  }

  async explain(input: MerchantGenerativeExplanationInput, signal?: AbortSignal): Promise<MerchantGenerativeExplanation> {
    if (!inputIsCoherent(input)) return neutralFallback;
    const fallback = deterministicFallback(input.deterministic);
    if (!input.deterministic.visible || !this.provider || signal?.aborted) return fallback;

    const request = requestFor(input);
    try {
      const response = await this.provider.generateExplanation(request, signal);
      if (signal?.aborted || !validResponse(response, input)) return fallback;
      return Object.freeze({ ...input.deterministic, source: 'generative_validated' });
    } catch {
      return fallback;
    }
  }
}

function requestFor(input: MerchantGenerativeExplanationInput): MerchantGenerativeExplanationRequest {
  return Object.freeze({
    promptVersion: merchantGenerativeExplanationPrompt.version,
    locale: input.locale,
    recommendation: input.intelligence.recommendation,
    reason: input.intelligence.reason,
    deterministicHeadline: input.deterministic.headline,
    deterministicBody: input.deterministic.body,
    ...(input.deterministic.actionLabel === undefined ? {} : { deterministicActionLabel: input.deterministic.actionLabel }),
    userActionAvailable: input.intelligence.userActionAvailable,
    tone: input.deterministic.tone,
  });
}

function inputIsCoherent(input: MerchantGenerativeExplanationInput): boolean {
  if (!input || (input.locale !== 'en' && input.locale !== 'am')) return false;
  const intelligence = input.intelligence;
  const deterministic = input.deterministic;
  return Boolean(intelligence && deterministic &&
    supportedSemantics[intelligence.reason] === intelligence.recommendation &&
    deterministic.reason === intelligence.reason &&
    deterministic.userActionAvailable === intelligence.userActionAvailable &&
    boundedText(deterministic.headline, maximumHeadlineLength) &&
    boundedText(deterministic.body, maximumBodyLength));
}

function validResponse(value: unknown, input: MerchantGenerativeExplanationInput): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  const keys = Object.keys(item).sort();
  if (keys.length !== 3 || keys[0] !== 'body' || keys[1] !== 'headline' || keys[2] !== 'locale') return false;
  if (item.locale !== input.locale || !boundedText(item.headline, maximumHeadlineLength) ||
      !boundedText(item.body, maximumBodyLength)) return false;
  return item.headline === input.deterministic.headline && item.body === input.deterministic.body;
}

function boundedText(value: unknown, maximum: number): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= maximum &&
    value === value.trim() && !/[\u0000-\u001f\u007f]/u.test(value);
}

function deterministicFallback(value: MerchantOperationalIntelligenceLanguage): MerchantGenerativeExplanation {
  return Object.freeze({ ...value, source: 'deterministic_fallback' });
}

const neutralFallback: MerchantGenerativeExplanation = Object.freeze({
  headline: 'Status unavailable',
  body: 'AYO cannot safely explain this status right now.',
  tone: 'neutral',
  reason: 'UNSUPPORTED_ACK_STATE',
  userActionAvailable: false,
  visible: false,
  source: 'deterministic_fallback',
});
