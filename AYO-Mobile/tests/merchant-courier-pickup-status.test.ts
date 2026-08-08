import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MerchantCourierPickupContractError,
  parseMerchantCourierPickupStatus,
} from '../domain/merchant-courier-pickup-status.ts';

const pickupId = '11111111-1111-4111-8111-111111111111';
const base = {
  pickup_id: pickupId,
  state: 'arrived_at_merchant',
  version: 3,
  arrived_at: '2026-08-08T10:00:00Z',
  merchant_acknowledged_at: null,
  waiting_duration_seconds: null,
  terminal_reason: null,
  updated_at: '2026-08-08T10:00:00Z',
  presentation_action: 'acknowledge_arrival',
};

test('all exact merchant lifecycle and action combinations parse', () => {
  const valid = [
    ['courier_assigned', 'none'],
    ['travelling_to_merchant', 'none'],
    ['arrived_at_merchant', 'acknowledge_arrival'],
    ['arrived_at_merchant', 'none'],
    ['waiting_for_pickup', 'none'],
    ['pickup_attempt_ended_before_custody', 'none'],
  ] as const;
  for (const [state, presentationAction] of valid) {
    const value = parseMerchantCourierPickupStatus({ ...base, state, presentation_action: presentationAction });
    assert.equal(value.state, state);
    assert.equal(value.presentationAction, presentationAction);
    assert.ok(Object.isFrozen(value));
  }
});

test('ARRIVED plus none is valid when server suppresses stale-assignment authority', () => {
  const value = parseMerchantCourierPickupStatus({ ...base, presentation_action: 'none' });
  assert.equal(value.state, 'arrived_at_merchant');
  assert.equal(value.arrivedAt, base.arrived_at);
  assert.equal(value.presentationAction, 'none');
});

test('ARRIVED requires its canonical arrival timestamp for every presentation action', () => {
  assert.equal(parseMerchantCourierPickupStatus(base).presentationAction, 'acknowledge_arrival');
  for (const presentation_action of ['acknowledge_arrival', 'none']) {
    assert.throws(
      () => parseMerchantCourierPickupStatus({ ...base, arrived_at: null, presentation_action }),
      MerchantCourierPickupContractError,
    );
  }
});

test('acknowledge arrival fails closed outside ARRIVED', () => {
  for (const state of ['courier_assigned', 'travelling_to_merchant', 'waiting_for_pickup', 'pickup_attempt_ended_before_custody']) {
    assert.throws(
      () => parseMerchantCourierPickupStatus({ ...base, state }),
      MerchantCourierPickupContractError,
    );
  }
});

test('unknown and missing state or action fail closed without fallback', () => {
  assert.throws(() => parseMerchantCourierPickupStatus({ ...base, state: 'unknown' }), MerchantCourierPickupContractError);
  assert.throws(() => parseMerchantCourierPickupStatus({ ...base, state: undefined }), MerchantCourierPickupContractError);
  assert.throws(() => parseMerchantCourierPickupStatus({ ...base, presentation_action: 'start_travel' }), MerchantCourierPickupContractError);
  assert.throws(() => parseMerchantCourierPickupStatus({ ...base, presentation_action: undefined }), MerchantCourierPickupContractError);
});

test('the exact field and primitive contract fails closed', () => {
  const { updated_at: _removed, ...missing } = base;
  for (const value of [
    { ...base, extra: true },
    missing,
    { ...base, pickup_id: 'pickup-1' },
    { ...base, version: 0 },
    { ...base, version: 1.5 },
    { ...base, updated_at: 'not-an-instant' },
    { ...base, arrived_at: 42 },
    { ...base, waiting_duration_seconds: -1 },
    { ...base, waiting_duration_seconds: 1.5 },
    { ...base, terminal_reason: 'anything' },
  ]) assert.throws(() => parseMerchantCourierPickupStatus(value), MerchantCourierPickupContractError);
});

test('the exact public terminal reason union is preserved', () => {
  const reasons = [
    'assignment_closed_or_revoked', 'merchant_location_unreachable', 'merchant_not_found',
    'merchant_unavailable', 'order_not_ready', 'readiness_corrected',
    'courier_unable_to_continue', 'authority_or_identity_failure',
    'duplicate_or_invalid_attempt', 'other_review_required',
  ] as const;
  for (const reason of reasons) {
    assert.equal(parseMerchantCourierPickupStatus({ ...base, terminal_reason: reason }).terminalReason, reason);
  }
});

test('the immutable projection contains only public server fields', () => {
  const value = parseMerchantCourierPickupStatus(base);
  assert.deepEqual(Object.keys(value), [
    'pickupId', 'state', 'version', 'arrivedAt', 'merchantAcknowledgedAt',
    'waitingDurationSeconds', 'terminalReason', 'updatedAt', 'presentationAction',
  ]);
  assert.ok(!('merchantId' in value));
  assert.ok(!('currentAssignment' in value));
  assert.ok(!('idempotencyKey' in value));
});
