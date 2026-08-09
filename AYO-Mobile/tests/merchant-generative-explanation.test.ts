import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  MerchantGenerativeExplanationGateway,
  merchantGenerativeExplanationPrompt,
  type MerchantGenerativeExplanationProvider,
  type MerchantGenerativeExplanationRequest,
} from '../domain/merchant-generative-explanation.ts';
import { recommendMerchantOperationalAction } from '../domain/merchant-operational-intelligence.ts';
import { explainMerchantOperationalIntelligence } from '../localization/merchant-operational-intelligence.ts';

const intelligence = recommendMerchantOperationalAction({ acknowledgementStatus: 'idle', canAcknowledgeArrival: true, canReconcileAcknowledgeArrival: false });
const deterministic = explainMerchantOperationalIntelligence(intelligence, 'en');
const input = Object.freeze({ locale: 'en' as const, intelligence, deterministic });
const validResponse = Object.freeze({ locale: 'en', headline: deterministic.headline, body: deterministic.body });

class RecordingProvider implements MerchantGenerativeExplanationProvider {
  requests: MerchantGenerativeExplanationRequest[] = [];
  calls = 0;
  private readonly response: unknown;
  private readonly failure?: Error;
  constructor(response: unknown = validResponse, failure?: Error) {
    this.response = response;
    this.failure = failure;
  }
  async generateExplanation(request: MerchantGenerativeExplanationRequest): Promise<unknown> {
    this.calls += 1;
    this.requests.push(request);
    if (this.failure) throw this.failure;
    return this.response;
  }
}

test('builds one frozen privacy-minimal explanation request with no command custody', async () => {
  const provider = new RecordingProvider();
  const result = await new MerchantGenerativeExplanationGateway(provider).explain(input);
  assert.equal(result.source, 'generative_validated');
  assert.equal(provider.calls, 1);
  assert.deepEqual(Object.keys(provider.requests[0]).sort(), [
    'deterministicActionLabel', 'deterministicBody', 'deterministicHeadline', 'locale',
    'promptVersion', 'reason', 'recommendation', 'tone', 'userActionAvailable',
  ]);
  assert.equal(Object.isFrozen(provider.requests[0]), true);
  assert.doesNotMatch(JSON.stringify(provider.requests[0]), /merchantId|orderId|pickupId|controller|scope|attempt|key|token|customer|address|location|payment/i);
});

test('provider and result contracts expose explanation only and remain immutable', async () => {
  const result = await new MerchantGenerativeExplanationGateway(new RecordingProvider()).explain(input);
  assert.deepEqual(Object.keys(result).sort(), ['actionLabel', 'body', 'headline', 'reason', 'source', 'tone', 'userActionAvailable', 'visible']);
  assert.equal(Object.isFrozen(result), true);
  assert.equal('execute' in result || 'acknowledge' in result || 'reconcile' in result || 'retry' in result, false);
});

test('strictly rejects malformed, missing, extra, empty, control-character, and overlong output', async () => {
  const invalid = [null, {}, { locale: 'en', headline: deterministic.headline },
    { ...validResponse, tool: 'acknowledge' }, { ...validResponse, headline: '' },
    { ...validResponse, headline: 'x'.repeat(81) }, { ...validResponse, body: 'x'.repeat(241) },
    { ...validResponse, body: 'unsafe\ntext' }, { ...validResponse, locale: 'am' }];
  for (const response of invalid) {
    const result = await new MerchantGenerativeExplanationGateway(new RecordingProvider(response)).explain(input);
    assert.equal(result.source, 'deterministic_fallback');
    assert.equal(result.headline, deterministic.headline);
  }
});

test('rejects prose that changes actionability, invents work, or contradicts semantic truth', async () => {
  const noAction = recommendMerchantOperationalAction({ acknowledgementStatus: 'idle', canAcknowledgeArrival: false, canReconcileAcknowledgeArrival: false });
  const hidden = explainMerchantOperationalIntelligence(noAction, 'en');
  const hiddenProvider = new RecordingProvider({ locale: 'en', headline: 'Act now', body: 'Tap acknowledge now.' });
  const hiddenResult = await new MerchantGenerativeExplanationGateway(hiddenProvider).explain({ locale: 'en', intelligence: noAction, deterministic: hidden });
  assert.equal(hiddenProvider.calls, 0);
  assert.equal(hiddenResult.visible, false);
  assert.equal(hiddenResult.userActionAvailable, false);

  const contradictions = [
    { ...validResponse, body: 'The acknowledgement is pending.' },
    { ...validResponse, body: 'The acknowledgement succeeded.' },
    { ...validResponse, body: 'Check status now.' },
  ];
  for (const response of contradictions) {
    assert.equal((await new MerchantGenerativeExplanationGateway(new RecordingProvider(response)).explain(input)).source, 'deterministic_fallback');
  }
});

test('confirmed and uncertain outcomes cannot be rewritten into contradictory operational claims', async () => {
  const confirmed = recommendMerchantOperationalAction({ acknowledgementStatus: 'applied', canAcknowledgeArrival: false, canReconcileAcknowledgeArrival: false });
  const confirmedCopy = explainMerchantOperationalIntelligence(confirmed, 'en');
  const pending = new RecordingProvider({ locale: 'en', headline: confirmedCopy.headline, body: 'The acknowledgement is still pending.' });
  assert.equal((await new MerchantGenerativeExplanationGateway(pending).explain({ locale: 'en', intelligence: confirmed, deterministic: confirmedCopy })).source, 'deterministic_fallback');

  const uncertain = recommendMerchantOperationalAction({ acknowledgementStatus: 'outcome_unknown', canAcknowledgeArrival: false, canReconcileAcknowledgeArrival: false });
  const uncertainCopy = explainMerchantOperationalIntelligence(uncertain, 'en');
  const falseSuccess = new RecordingProvider({ locale: 'en', headline: uncertainCopy.headline, body: 'The acknowledgement succeeded.' });
  const result = await new MerchantGenerativeExplanationGateway(falseSuccess).explain({ locale: 'en', intelligence: uncertain, deterministic: uncertainCopy });
  assert.equal(falseSuccess.calls, 1);
  assert.equal(result.source, 'deterministic_fallback');
  assert.equal(result.userActionAvailable, false);
});

test('supported Amharic locale preserves the locked localized explanation exactly', async () => {
  const words = explainMerchantOperationalIntelligence(intelligence, 'am');
  const provider = new RecordingProvider({ locale: 'am', headline: words.headline, body: words.body });
  const result = await new MerchantGenerativeExplanationGateway(provider).explain({ locale: 'am', intelligence, deterministic: words });
  assert.equal(result.source, 'generative_validated');
  assert.equal(result.headline, words.headline);
  assert.equal(result.body, words.body);
});

test('provider exceptions, cancellation, and disabled mode preserve immediate Phase 2 fallback', async () => {
  assert.equal((await new MerchantGenerativeExplanationGateway().explain(input)).source, 'deterministic_fallback');
  assert.equal((await new MerchantGenerativeExplanationGateway(new RecordingProvider(validResponse, new Error('offline'))).explain(input)).source, 'deterministic_fallback');
  const controller = new AbortController();
  controller.abort();
  const provider = new RecordingProvider();
  assert.equal((await new MerchantGenerativeExplanationGateway(provider).explain(input, controller.signal)).source, 'deterministic_fallback');
  assert.equal(provider.calls, 0);
});

test('generated output must preserve exact locked Phase 2 truth and locale', async () => {
  const first = await new MerchantGenerativeExplanationGateway(new RecordingProvider()).explain(input);
  const second = await new MerchantGenerativeExplanationGateway(new RecordingProvider()).explain(input);
  assert.deepEqual(first, second);
  assert.equal(first.headline, deterministic.headline);
  assert.equal(first.body, deterministic.body);
  assert.equal(first.userActionAvailable, intelligence.userActionAvailable);
});

test('incoherent Phase 1 and Phase 2 evidence fails closed before provider execution', async () => {
  const provider = new RecordingProvider();
  const corrupted = { ...input, deterministic: { ...deterministic, reason: 'ACK_CONFIRMED' as const, userActionAvailable: true } };
  const result = await new MerchantGenerativeExplanationGateway(provider).explain(corrupted);
  assert.equal(provider.calls, 0);
  assert.equal(result.source, 'deterministic_fallback');
  assert.equal(result.userActionAvailable, false);
  assert.equal(result.visible, false);
  assert.equal(result.reason, 'UNSUPPORTED_ACK_STATE');
});

test('prompt is static, versioned, bounded, and explicitly prohibits authority invention', () => {
  assert.equal(merchantGenerativeExplanationPrompt.version, 'merchant_ack_explanation_v1');
  assert.equal(Object.isFrozen(merchantGenerativeExplanationPrompt), true);
  assert.equal(Object.isFrozen(merchantGenerativeExplanationPrompt.instructions), true);
  assert.match(merchantGenerativeExplanationPrompt.instructions.join(' '), /Do not invent facts, actions, authority/);
});

test('source contains no model SDK, secret, tool, memory, RAG, embedding, or networking implementation', async () => {
  const source = await readFile(new URL('../domain/merchant-generative-explanation.ts', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /openai|anthropic|gemini|api[_-]?key|fetch\(|XMLHttpRequest|WebSocket|vector database|embedding|conversation history/i);
  assert.doesNotMatch(source, /execute\(|dispatch\(|post\(|acknowledgeArrival\(|reconcileAcknowledgeArrival\(/);
});
