import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { MerchantGenerativeExplanationRequest } from '../domain/merchant-generative-explanation.ts';
import { MerchantGenerativeExplanationService } from '../services/merchant-generative-explanation.ts';

const request: MerchantGenerativeExplanationRequest = Object.freeze({
  promptVersion: 'merchant_ack_explanation_v1',
  locale: 'en',
  recommendation: 'acknowledge_arrival',
  reason: 'ACK_ALLOWED_BY_CAPABILITY',
  deterministicHeadline: 'Courier has arrived',
  deterministicBody: "You can acknowledge the courier's arrival now.",
  deterministicActionLabel: 'Acknowledge arrival',
  userActionAvailable: true,
  tone: 'informative',
});

function sessions() {
  return {
    accessToken: async () => 'mobile-token',
    forceRefresh: async () => undefined,
  } as never;
}

test('adapter calls only the authenticated bounded AYO endpoint with exact Phase 3 semantics', async () => {
  let call: { url: string; init?: RequestInit } | undefined;
  const transport = async (url: string | URL | Request, init?: RequestInit) => {
    call = { url: String(url), init };
    return new Response(JSON.stringify({ locale: 'en', headline: request.deterministicHeadline, body: request.deterministicBody }), {
      status: 200, headers: { 'content-type': 'application/json' },
    });
  };
  const service = new MerchantGenerativeExplanationService('https://api.ayo.example/api', sessions(), transport as typeof fetch);
  const signal = new AbortController().signal;
  const result = await service.generateExplanation(request, signal);
  assert.deepEqual(result, { locale: 'en', headline: request.deterministicHeadline, body: request.deterministicBody });
  assert.equal(call?.url, 'https://api.ayo.example/api/mobile/merchant-intelligence/generative-explanation');
  assert.equal(call?.init?.method, 'POST');
  assert.equal(call?.init?.signal instanceof AbortSignal, true);
  assert.equal((call?.init?.headers as Record<string, string>).Authorization, 'Bearer mobile-token');
  assert.deepEqual(JSON.parse(String(call?.init?.body)), {
    promptVersion: request.promptVersion,
    locale: request.locale,
    recommendation: request.recommendation,
    reason: request.reason,
    userActionAvailable: request.userActionAvailable,
    tone: request.tone,
  });
  assert.equal(String(call?.init?.body).includes(request.deterministicHeadline), false);
  assert.equal(String(call?.init?.body).includes(request.deterministicBody), false);
  assert.equal(String(call?.init?.body).includes(request.deterministicActionLabel ?? ''), false);
  for (const prohibited of ['merchantId', 'orderId', 'pickupId', 'messages', 'model', 'provider', 'tools', 'secret', 'attemptId', 'idempotencyKey']) {
    assert.equal(String(call?.init?.body).includes(prohibited), false);
  }
});

test('adapter propagates cancellation and performs no automatic retry', async () => {
  let calls = 0;
  const transport = async (_url: string | URL | Request, init?: RequestInit) => {
    calls += 1;
    return await new Promise<Response>((_resolve, reject) => {
      if (init?.signal?.aborted) reject(new Error('aborted'));
      else init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    });
  };
  const service = new MerchantGenerativeExplanationService('https://api.ayo.example/api', sessions(), transport as typeof fetch);
  const controller = new AbortController();
  const flight = service.generateExplanation(request, controller.signal);
  controller.abort();
  await assert.rejects(flight);
  assert.equal(calls, 1);
});
