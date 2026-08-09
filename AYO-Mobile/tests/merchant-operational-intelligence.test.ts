import assert from 'node:assert/strict';
import test from 'node:test';

import { recommendMerchantOperationalAction, type MerchantAcknowledgementPresentationStatus, type MerchantOperationalIntelligenceInput } from '../domain/merchant-operational-intelligence.ts';

const evaluate = (acknowledgementStatus: MerchantAcknowledgementPresentationStatus, canAcknowledgeArrival = false, canReconcileAcknowledgeArrival = false) =>
  recommendMerchantOperationalAction({ acknowledgementStatus, canAcknowledgeArrival, canReconcileAcknowledgeArrival });

test('capability predicates are the final authority for actionable recommendations', () => {
  assert.deepEqual(evaluate('idle', true), { recommendation: 'acknowledge_arrival', reason: 'ACK_ALLOWED_BY_CAPABILITY', userActionAvailable: true });
  assert.deepEqual(evaluate('idle'), { recommendation: 'no_action', reason: 'NO_CURRENT_ACK_ACTION', userActionAvailable: false });
  assert.deepEqual(evaluate('outcome_unknown', false, true), { recommendation: 'check_acknowledgement_status', reason: 'ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE', userActionAvailable: true });
  assert.deepEqual(evaluate('outcome_unknown'), { recommendation: 'acknowledgement_issue', reason: 'ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION', userActionAvailable: false });
  assert.deepEqual(evaluate('retry_same_attempt', true), { recommendation: 'retry_same_acknowledgement', reason: 'ACK_SAME_ATTEMPT_RETRY_AVAILABLE', userActionAvailable: true });
  assert.deepEqual(evaluate('retry_same_attempt'), { recommendation: 'acknowledgement_issue', reason: 'ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED', userActionAvailable: false });
  assert.deepEqual(evaluate('rejected', true), { recommendation: 'retry_acknowledgement', reason: 'ACK_RETRY_ALLOWED_BY_CAPABILITY', userActionAvailable: true });
  assert.deepEqual(evaluate('rejected'), { recommendation: 'acknowledgement_issue', reason: 'ACK_REJECTED_NO_CURRENT_ACTION', userActionAvailable: false });
});

test('in-progress and settled states explain truth without recommending duplicate action', () => {
  for (const [status, recommendation, reason] of [
    ['submitting', 'acknowledging_arrival', 'ACK_IN_PROGRESS'],
    ['applied', 'arrival_acknowledged', 'ACK_CONFIRMED'],
    ['reconciling', 'checking_acknowledgement_status', 'ACK_RECONCILIATION_IN_PROGRESS'],
  ] as const) assert.deepEqual(evaluate(status), { recommendation, reason, userActionAvailable: false });
  assert.deepEqual(evaluate('invalidated'), { recommendation: 'no_action', reason: 'ACK_AUTHORITY_CHANGED', userActionAvailable: false });
});

test('display context cannot authorize a command or override false predicates', () => {
  const displayContext = Object.freeze({ pickupStatus: 'arrived', orderState: 'ready_for_pickup' });
  assert.deepEqual({ displayContext, intelligence: evaluate('idle') }.intelligence, { recommendation: 'no_action', reason: 'NO_CURRENT_ACK_ACTION', userActionAvailable: false });
});

test('contracts expose no command custody or private authority identifiers', () => {
  const input: MerchantOperationalIntelligenceInput = Object.freeze({ acknowledgementStatus: 'idle', canAcknowledgeArrival: true, canReconcileAcknowledgeArrival: false });
  const output = recommendMerchantOperationalAction(input);
  assert.deepEqual(Object.keys(input).sort(), ['acknowledgementStatus', 'canAcknowledgeArrival', 'canReconcileAcknowledgeArrival']);
  assert.deepEqual(Object.keys(output).sort(), ['reason', 'recommendation', 'userActionAvailable']);
  for (const forbidden of ['merchantId', 'orderId', 'pickupId', 'controller', 'scope', 'attempt', 'idempotencyKey', 'service', 'transport', 'execute', 'acknowledge', 'reconcile', 'retry']) {
    assert.equal(forbidden in input, false); assert.equal(forbidden in output, false);
  }
});

test('evaluation is synchronous, deterministic, immutable, and creates no side effects', () => {
  let attempts = 0; let keys = 0; let gets = 0; let posts = 0; let timers = 0;
  const input = Object.freeze({ acknowledgementStatus: 'idle' as const, canAcknowledgeArrival: true, canReconcileAcknowledgeArrival: false });
  const first = recommendMerchantOperationalAction(input); const second = recommendMerchantOperationalAction(input);
  assert.deepEqual(first, second); assert.equal(first, second); assert.ok(Object.isFrozen(first));
  assert.deepEqual({ attempts, keys, gets, posts, timers }, { attempts: 0, keys: 0, gets: 0, posts: 0, timers: 0 });
});

test('unknown or malformed presentation evidence fails closed', () => {
  assert.deepEqual(recommendMerchantOperationalAction({ acknowledgementStatus: 'future_state', canAcknowledgeArrival: true, canReconcileAcknowledgeArrival: true } as unknown as MerchantOperationalIntelligenceInput), { recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false });
  assert.deepEqual(recommendMerchantOperationalAction({ acknowledgementStatus: 'idle', canAcknowledgeArrival: 'yes', canReconcileAcknowledgeArrival: true } as unknown as MerchantOperationalIntelligenceInput), { recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false });
  assert.deepEqual(evaluate('idle', true, true), { recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false });
  assert.deepEqual(evaluate('submitting', true), { recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false });
});
