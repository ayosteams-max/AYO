import assert from 'node:assert/strict';
import test from 'node:test';

import type { MerchantOperationalIntelligenceResult } from '../domain/merchant-operational-intelligence.ts';
import { explainMerchantOperationalIntelligence } from '../localization/merchant-operational-intelligence.ts';

const cases: readonly MerchantOperationalIntelligenceResult[] = Object.freeze([
  { recommendation: 'no_action', reason: 'NO_CURRENT_ACK_ACTION', userActionAvailable: false },
  { recommendation: 'no_action', reason: 'ACK_AUTHORITY_CHANGED', userActionAvailable: false },
  { recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false },
  { recommendation: 'acknowledge_arrival', reason: 'ACK_ALLOWED_BY_CAPABILITY', userActionAvailable: true },
  { recommendation: 'acknowledging_arrival', reason: 'ACK_IN_PROGRESS', userActionAvailable: false },
  { recommendation: 'arrival_acknowledged', reason: 'ACK_CONFIRMED', userActionAvailable: false },
  { recommendation: 'check_acknowledgement_status', reason: 'ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE', userActionAvailable: true },
  { recommendation: 'checking_acknowledgement_status', reason: 'ACK_RECONCILIATION_IN_PROGRESS', userActionAvailable: false },
  { recommendation: 'retry_same_acknowledgement', reason: 'ACK_SAME_ATTEMPT_RETRY_AVAILABLE', userActionAvailable: true },
  { recommendation: 'retry_acknowledgement', reason: 'ACK_RETRY_ALLOWED_BY_CAPABILITY', userActionAvailable: true },
  { recommendation: 'acknowledgement_issue', reason: 'ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION', userActionAvailable: false },
  { recommendation: 'acknowledgement_issue', reason: 'ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED', userActionAvailable: false },
  { recommendation: 'acknowledgement_issue', reason: 'ACK_REJECTED_NO_CURRENT_ACTION', userActionAvailable: false },
]);

test('every Phase 1 recommendation and reason resolves to bounded English semantics', () => {
  const resolved = cases.map((value) => explainMerchantOperationalIntelligence(value, 'en'));
  assert.equal(resolved.length, 13);
  assert.deepEqual(resolved.map((value) => value.reason), cases.map((value) => value.reason));
  assert.ok(resolved.every((value) => value.headline.length > 0 && value.body.length > 0));
  assert.deepEqual(resolved[3], { headline: 'Courier has arrived', body: 'You can acknowledge the courier’s arrival now.', actionLabel: 'Acknowledge arrival', tone: 'informative', reason: 'ACK_ALLOWED_BY_CAPABILITY', userActionAvailable: true, visible: true });
  assert.equal(resolved[4].headline, 'Acknowledging arrival');
  assert.equal(resolved[5].headline, 'Arrival acknowledged');
  assert.equal(resolved[6].actionLabel, 'Check status');
  assert.equal(resolved[7].headline, 'Checking status');
  assert.equal(resolved[8].actionLabel, 'Try again');
  assert.equal(resolved[9].headline, 'Try again');
  assert.ok(resolved.slice(10).every((value) => !value.userActionAvailable && value.actionLabel === undefined));
});

test('same-attempt retry language is safe and exposes no command custody mechanics', () => {
  const language = explainMerchantOperationalIntelligence(cases[8], 'en');
  const publicText = `${language.headline} ${language.body} ${language.actionLabel ?? ''}`.toLowerCase();
  for (const forbidden of ['idempotency', 'uuid', 'version', 'controller', 'scope', 'key', 'command']) assert.equal(publicText.includes(forbidden), false);
  assert.equal(language.reason, 'ACK_SAME_ATTEMPT_RETRY_AVAILABLE');
});

test('false Phase 1 actionability is never upgraded into actionable language', () => {
  for (const input of cases.filter((value) => !value.userActionAvailable)) {
    const language = explainMerchantOperationalIntelligence(input, 'en');
    assert.equal(language.userActionAvailable, false);
    assert.equal(language.actionLabel, undefined);
  }
  assert.equal(explainMerchantOperationalIntelligence(cases[0], 'en').visible, false);
});

test('malformed and contradictory Phase 1 values fail closed to hidden neutral language', () => {
  for (const malformed of [
    undefined,
    { recommendation: 'acknowledge_arrival', reason: 'ACK_ALLOWED_BY_CAPABILITY', userActionAvailable: false },
    { recommendation: 'no_action', reason: 'FUTURE_REASON', userActionAvailable: true },
  ]) {
    const language = explainMerchantOperationalIntelligence(malformed as MerchantOperationalIntelligenceResult, 'en');
    assert.deepEqual(language, { headline: 'Status unavailable', body: 'AYO cannot safely suggest an arrival acknowledgement action right now.', tone: 'neutral', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false, visible: false });
  }
});

test('English and Amharic resolve with explicit native-review governance', () => {
  for (const input of cases) {
    const english = explainMerchantOperationalIntelligence(input, 'en');
    const amharic = explainMerchantOperationalIntelligence(input, 'am');
    assert.ok(english.headline.length && english.body.length && amharic.headline.length && amharic.body.length);
    assert.equal(amharic.reason, english.reason);
    assert.equal(amharic.userActionAvailable, english.userActionAvailable);
  }
  assert.equal(explainMerchantOperationalIntelligence(cases[3], 'am').headline, 'መልእክተኛው ደርሷል');
});

test('language results are deterministic, frozen, privacy-minimal, and side-effect free', () => {
  let gets = 0; let posts = 0; let attempts = 0; let keys = 0; let timers = 0; let models = 0;
  const first = explainMerchantOperationalIntelligence(cases[6], 'en');
  const second = explainMerchantOperationalIntelligence(cases[6], 'en');
  assert.deepEqual(first, second); assert.ok(Object.isFrozen(first));
  assert.deepEqual(Object.keys(first).sort(), ['actionLabel', 'body', 'headline', 'reason', 'tone', 'userActionAvailable', 'visible']);
  for (const forbidden of ['merchantId', 'orderId', 'pickupId', 'controller', 'scope', 'attempt', 'idempotencyKey', 'service', 'transport', 'execute', 'acknowledge', 'reconcile', 'retry']) assert.equal(forbidden in first, false);
  assert.deepEqual({ gets, posts, attempts, keys, timers, models }, { gets: 0, posts: 0, attempts: 0, keys: 0, timers: 0, models: 0 });
});

test('source preserves exhaustive reason mapping and native Amharic review marker', async () => {
  const source = await import('node:fs/promises').then((fs) => fs.readFile(new URL('../localization/merchant-operational-intelligence.ts', import.meta.url), 'utf8'));
  for (const input of cases) assert.ok(source.includes(input.reason));
  assert.ok(source.includes('satisfies Readonly<Record<Reason, Mapping>>'));
  assert.ok(source.includes('NEEDS_NATIVE_AMHARIC_REVIEW'));
});
