import assert from 'node:assert/strict';
import test from 'node:test';

import { MerchantCourierPickupContractError } from '../domain/merchant-courier-pickup-status.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { AuthenticatedReadTransport } from '../services/authenticated-read-transport.ts';
import { MerchantCourierPickupStatusService } from '../services/merchant-courier-pickup-status.ts';
import type { SessionManager } from '../services/session-manager.ts';

const merchantId = '11111111-1111-4111-8111-111111111111';
const orderId = '22222222-2222-4222-8222-222222222222';
const response = {
  pickup_id: '33333333-3333-4333-8333-333333333333',
  state: 'arrived_at_merchant',
  version: 3,
  arrived_at: '2026-08-08T10:00:00Z',
  merchant_acknowledged_at: null,
  waiting_duration_seconds: null,
  terminal_reason: null,
  updated_at: '2026-08-08T10:00:00Z',
  presentation_action: 'acknowledge_arrival',
};

test('one explicit load performs exactly one bounded authenticated GET', async () => {
  const calls: Array<{ path: string; signal?: AbortSignal }> = [];
  const controller = new AbortController();
  const service = new MerchantCourierPickupStatusService(async (path, signal) => {
    calls.push({ path, signal });
    return response;
  });

  const snapshot = await service.load(merchantId, orderId, controller.signal);

  assert.equal(snapshot.presentationAction, 'acknowledge_arrival');
  assert.deepEqual(calls, [{
    path: `/mobile/merchants/${merchantId}/orders/${orderId}/courier-pickup`,
    signal: controller.signal,
  }]);
});

test('malformed identifiers fail before authenticated network access', async () => {
  let calls = 0;
  const service = new MerchantCourierPickupStatusService(async () => { calls += 1; return response; });
  await assert.rejects(service.load('../merchant', orderId), MerchantCourierPickupContractError);
  await assert.rejects(service.load(merchantId, 'order/../other'), MerchantCourierPickupContractError);
  assert.equal(calls, 0);
});

test('malformed server response produces no partial snapshot', async () => {
  const service = new MerchantCourierPickupStatusService(async () => ({ ...response, presentation_action: 'mark_arrived' }));
  await assert.rejects(service.load(merchantId, orderId), MerchantCourierPickupContractError);
});

test('canonical authenticated-read errors pass through without custom retry', async () => {
  const expected = new PublicApiError('session_expired', 401);
  let calls = 0;
  const service = new MerchantCourierPickupStatusService(async () => { calls += 1; throw expected; });
  await assert.rejects(service.load(merchantId, orderId), (error: unknown) => error === expected);
  assert.equal(calls, 1);
});

test('service composes with canonical SessionManager authenticated transport', async () => {
  let authorization = '';
  let requests = 0;
  const sessions = { accessToken: async () => 'a'.repeat(64) } as SessionManager;
  const transport = new AuthenticatedReadTransport(
    'https://api.ayo.example',
    sessions,
    async (_input, init) => {
      requests += 1;
      authorization = String((init?.headers as Record<string, string>).Authorization);
      return new Response(JSON.stringify(response), { status: 200 });
    },
  );
  const service = new MerchantCourierPickupStatusService(transport.get.bind(transport));

  await service.load(merchantId, orderId);

  assert.equal(requests, 1);
  assert.equal(authorization, `Bearer ${'a'.repeat(64)}`);
});

test('the read service has no command, Custody, or secondary request path', async () => {
  const paths: string[] = [];
  const service = new MerchantCourierPickupStatusService(async (path) => { paths.push(path); return response; });
  await service.load(merchantId, orderId);
  assert.equal(paths.length, 1);
  assert.ok(paths.every((path) => !path.includes('/custody') && !path.includes('/acknowledge')));
  assert.equal(typeof (service as unknown as Record<string, unknown>).post, 'undefined');
});
