import assert from 'node:assert/strict';
import test from 'node:test';

import { MerchantOperationalOrderContractError, parseMerchantOperationalOrders } from '../domain/merchant-operational-order.ts';
import { MerchantOperationalOrderService } from '../services/merchant-operational-orders.ts';
import { merchantOperationalOrderCopy } from '../localization/merchant-operational-orders.ts';

const merchantId = '11111111-1111-4111-8111-111111111111';
const orderId = '22222222-2222-4222-8222-222222222222';

function view(overrides: Record<string, unknown> = {}) {
  return {
    order: {
      order_id: orderId, merchant_id: merchantId, merchant_display_name: 'AYO Market', state: 'ready_for_pickup',
      lines: [{ item_id: '33333333-3333-4333-8333-333333333333', item_version: 1, name: 'Ethiopian coffee', kind: 'product', category_id: null, quantity: 2, unit_price_minor: 1000, line_total_minor: 2000, currency: 'ETB', modifier_selections: [], customer_instructions: null }],
      pricing: { authority: 'commerce_pricing', policy_version: 'commerce.v1', subtotal_minor: 2000, currency: 'ETB', evidence_hash: 'a'.repeat(64) },
      evidence_hash: 'b'.repeat(64), version: 4, created_at: '2026-08-09T01:00:00Z',
      ...overrides,
    }, timeline: [], rejection: null,
  };
}

function whitespaceView() {
  const base = view({
    merchant_display_name: ' AYO Market ',
    state: 'rejected',
    lines: [{ item_id: '33333333-3333-4333-8333-333333333333', item_version: 1, name: ' Ethiopian coffee ', kind: ' product ', category_id: null, quantity: 2, unit_price_minor: 1000, line_total_minor: 2000, currency: 'ETB', modifier_selections: [], customer_instructions: null }],
    pricing: { authority: 'commerce_pricing', policy_version: ' commerce.v1 ', subtotal_minor: 2000, currency: 'ETB', evidence_hash: 'a'.repeat(64) },
  });
  return { ...base, rejection: { order_id: orderId, customer_reason_code: 'merchant_declined', customer_message: ' This item cannot be prepared today. ', internal_merchant_note: null, decided_by_identity_id: '44444444-4444-4444-8444-444444444444', decided_at: '2026-08-09T01:01:00Z' } };
}

test('strict list parser returns only bounded merchant-safe operational fields', () => {
  const result = parseMerchantOperationalOrders([view()], merchantId);
  assert.deepEqual(result, [{ orderId, merchantId, state: 'ready_for_pickup', version: 4, createdAt: '2026-08-09T01:00:00Z' }]);
  assert.ok(Object.isFrozen(result)); assert.ok(Object.isFrozen(result[0]));
  assert.deepEqual(Object.keys(result[0]).sort(), ['createdAt', 'merchantId', 'orderId', 'state', 'version']);
});

test('one malformed or cross-merchant row rejects the entire canonical list', () => {
  for (const malformed of [
    [view({ state: 'invented' })],
    [view({ merchant_id: '44444444-4444-4444-8444-444444444444' })],
    [{ ...view(), extra: true }],
    Array.from({ length: 26 }, () => view()),
  ]) assert.throws(() => parseMerchantOperationalOrders(malformed, merchantId), MerchantOperationalOrderContractError);
});

test('backend-valid bounded strings preserve surrounding whitespace without invalidating the list', () => {
  const result = parseMerchantOperationalOrders([whitespaceView()], merchantId);
  assert.equal(result.length, 1);
  assert.equal(result[0].orderId, orderId);
  assert.equal(result[0].state, 'rejected');
});

test('genuinely malformed bounded strings, identifiers, hashes, literals and patterns still reject the whole list', () => {
  const malformed = [
    view({ merchant_display_name: 'A' }),
    view({ merchant_display_name: 'A'.repeat(121) }),
    view({ merchant_display_name: 42 }),
    view({ state: 'invented' }),
    view({ order_id: 'not-a-uuid' }),
    view({ evidence_hash: 'not-a-hash' }),
    { ...whitespaceView(), rejection: { ...whitespaceView().rejection, customer_reason_code: 'Invalid reason' } },
    { ...view(), timeline: [{ event_id: '55555555-5555-4555-8555-555555555555', order_id: orderId, merchant_id: merchantId, event_type: 'Invalid event', from_state: null, to_state: 'ready_for_pickup', actor_identity_id: null, order_version: 1, customer_reason_code: null, occurred_at: '2026-08-09T01:00:00Z' }] },
  ];
  for (const invalid of malformed) {
    assert.throws(() => parseMerchantOperationalOrders([view(), invalid], merchantId), MerchantOperationalOrderContractError);
  }
});

test('service performs one bounded authenticated list GET and no detail request', async () => {
  const calls: string[] = [];
  const service = new MerchantOperationalOrderService(async (path) => { calls.push(path); return [view()]; });
  assert.equal((await service.list(merchantId))[0].orderId, orderId);
  assert.deepEqual(calls, [`/mobile/merchants/${merchantId}/orders?limit=25`]);
});

test('English and Amharic order-surface keys are complete with explicit native-review governance', () => {
  assert.deepEqual(Object.keys(merchantOperationalOrderCopy.en).sort(), Object.keys(merchantOperationalOrderCopy.am).sort());
  for (const locale of ['en', 'am'] as const) for (const value of Object.values(merchantOperationalOrderCopy[locale])) assert.ok(value.trim());
});
