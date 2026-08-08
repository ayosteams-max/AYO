import assert from 'node:assert/strict';
import test from 'node:test';

import { createMarkArrivedAttempt, MarkArrivedAttemptInvalidError, MarkArrivedContractError, MarkArrivedOutcomeUnknownError, MarkArrivedRejectedError, parseMarkArrivedResult, reconcileMarkArrivedRead, type MarkArrivedCommandScope } from '../domain/courier-mark-arrived-command.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { CourierMarkArrivedCommandService, CourierMarkArrivedTransport } from '../services/courier-mark-arrived-command.ts';

const identityA = '11111111-1111-4111-8111-111111111111';
const identityB = '22222222-2222-4222-8222-222222222222';
const sessionA = '33333333-3333-4333-8333-333333333333';
const sessionB = '44444444-4444-4444-8444-444444444444';
const pickupA = '55555555-5555-4555-8555-555555555555';
const pickupB = '66666666-6666-4666-8666-666666666666';
const keyA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const keyB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const scope = (overrides: Partial<MarkArrivedCommandScope> = {}): MarkArrivedCommandScope => ({
  identityId: identityA, sessionId: sessionA, identityGeneration: 7, contextGeneration: 9,
  pickupId: pickupA, pickupVersion: 5, presentationAction: 'mark_arrived', ...overrides,
});

const result = (overrides: Record<string, unknown> = {}) => ({
  pickup_id: pickupA, state: 'arrived_at_merchant', version: 6,
  assigned_at: '2026-08-08T01:00:00Z', travelling_at: '2026-08-08T01:05:00Z', arrived_at: '2026-08-08T01:10:00Z',
  merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: '2026-08-08T01:10:00Z', ...overrides,
});

function pickup(state: 'travelling_to_merchant' | 'arrived_at_merchant' | 'waiting_for_pickup' | 'pickup_attempt_ended_before_custody', version: number, overrides: Record<string, unknown> = {}) {
  const arrived = state === 'arrived_at_merchant' || state === 'waiting_for_pickup';
  const waiting = state === 'waiting_for_pickup';
  return {
    pickup_id: pickupA, state, version, assigned_at: '2026-08-08T01:00:00Z', travelling_at: '2026-08-08T01:05:00Z',
    arrived_at: arrived ? '2026-08-08T01:10:00Z' : null, merchant_acknowledged_at: waiting ? '2026-08-08T01:12:00Z' : null,
    waiting_duration_seconds: waiting ? 0 : null, terminal_reason: state === 'pickup_attempt_ended_before_custody' ? 'courier_unable_to_continue' : null,
    updated_at: waiting ? '2026-08-08T01:12:00Z' : arrived ? '2026-08-08T01:10:00Z' : '2026-08-08T01:05:00Z',
    presentation_action: state === 'travelling_to_merchant' ? 'mark_arrived' : 'none', ...overrides,
  };
}

test('only an exact trusted mark-arrived scope creates one immutable secure attempt', () => {
  const generated = createMarkArrivedAttempt(scope());
  const first = createMarkArrivedAttempt(scope(), () => keyA);
  const second = createMarkArrivedAttempt(scope(), () => keyB);
  assert.match(generated.idempotencyKey, /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.deepEqual(first, { action: 'mark_arrived', pickupId: pickupA, expectedVersion: 5, idempotencyKey: keyA, identityId: identityA, sessionId: sessionA, identityGeneration: 7, contextGeneration: 9 });
  assert.equal(Object.isFrozen(first), true); assert.notEqual(first.idempotencyKey, second.idempotencyKey);
  assert.throws(() => createMarkArrivedAttempt(scope(), () => 'weak'), MarkArrivedAttemptInvalidError);
  assert.throws(() => createMarkArrivedAttempt(scope({ identityId: 'bad' }), () => keyA), MarkArrivedAttemptInvalidError);
  assert.throws(() => createMarkArrivedAttempt(scope({ sessionId: 'bad' }), () => keyA), MarkArrivedAttemptInvalidError);
  assert.throws(() => createMarkArrivedAttempt(scope({ pickupId: 'bad' }), () => keyA), MarkArrivedAttemptInvalidError);
  assert.throws(() => createMarkArrivedAttempt(scope({ pickupVersion: 0 }), () => keyA), MarkArrivedAttemptInvalidError);
  for (const presentationAction of ['start_travel', 'none']) assert.throws(() => createMarkArrivedAttempt({ ...scope(), presentationAction } as unknown as MarkArrivedCommandScope, () => keyA), MarkArrivedAttemptInvalidError);
});

test('every identity, session, generation, context, Pickup, version, and action change fails before transport', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  const changed = [
    scope({ identityId: identityB }), scope({ sessionId: sessionB }), scope({ identityGeneration: 8 }), scope({ contextGeneration: 10 }),
    scope({ pickupId: pickupB }), scope({ pickupVersion: 6 }), { ...scope(), presentationAction: 'start_travel' } as unknown as MarkArrivedCommandScope,
  ];
  for (const current of changed) {
    let posts = 0;
    const service = new CourierMarkArrivedCommandService({ post: async () => { posts += 1; return result(); } }, async () => pickup('travelling_to_merchant', 5), () => current);
    await assert.rejects(service.submit(attempt), MarkArrivedAttemptInvalidError); assert.equal(posts, 0);
  }
});

test('transport uses the canonical session, endpoint, exact body, key, and no location fields', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA); let captured: [string, RequestInit] | undefined; let restores = 0;
  const sessions = { restore: async () => { restores += 1; return { identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) }; }, forceRefresh: async () => undefined } as never;
  const transport = new CourierMarkArrivedTransport('https://api.example.test', sessions, async (input, init) => { captured = [String(input), init ?? {}]; return new Response(JSON.stringify(result()), { status: 200 }); });
  await transport.post(attempt, () => true);
  assert.equal(restores, 1); assert.equal(captured?.[0], `https://api.example.test/mobile/courier-pickups/${pickupA}/actions`);
  assert.equal((captured?.[1].headers as Record<string, string>)['Idempotency-Key'], keyA);
  assert.deepEqual(JSON.parse(String(captured?.[1].body)), { expected_version: 5, action: 'mark_arrived' });
});

test('stale identity/session and scope changes during restore prevent POST', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  for (const restored of [undefined, { identityId: identityB, sessionId: sessionA, accessToken: 't'.repeat(32) }, { identityId: identityA, sessionId: sessionB, accessToken: 't'.repeat(32) }]) {
    let posts = 0; const transport = new CourierMarkArrivedTransport('https://api.example.test', { restore: async () => restored, forceRefresh: async () => undefined } as never, async () => { posts += 1; return new Response(); });
    await assert.rejects(transport.post(attempt, () => true), MarkArrivedAttemptInvalidError); assert.equal(posts, 0);
  }
  let current: MarkArrivedCommandScope | undefined = scope(); let resolveRestore!: (value: unknown) => void; let posts = 0;
  const sessions = { restore: () => new Promise((resolve) => { resolveRestore = resolve; }), forceRefresh: async () => undefined } as never;
  const service = new CourierMarkArrivedCommandService(new CourierMarkArrivedTransport('https://api.example.test', sessions, async () => { posts += 1; return new Response(JSON.stringify(result()), { status: 200 }); }), async () => pickup('travelling_to_merchant', 5), () => current);
  const pending = service.submit(attempt); await Promise.resolve(); current = undefined; resolveRestore({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) });
  await assert.rejects(pending, MarkArrivedAttemptInvalidError); assert.equal(posts, 0);
});

test('auth refresh rechecks scope and preserves the exact attempt and key', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA); let current: MarkArrivedCommandScope | undefined = scope(); let resolveRefresh!: (value: unknown) => void; const keys: string[] = [];
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: () => new Promise((resolve) => { resolveRefresh = resolve; }) } as never;
  const service = new CourierMarkArrivedCommandService(new CourierMarkArrivedTransport('https://api.example.test', sessions, async (_input, init) => { keys.push((init?.headers as Record<string, string>)['Idempotency-Key']); return new Response('', { status: 401 }); }), async () => pickup('travelling_to_merchant', 5), () => current);
  const pending = service.submit(attempt); while (!resolveRefresh) await Promise.resolve(); current = undefined;
  resolveRefresh({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(32) });
  await assert.rejects(pending, MarkArrivedAttemptInvalidError); assert.deepEqual(keys, [keyA]);

  let calls = 0; const retryKeys: string[] = [];
  const healthy = new CourierMarkArrivedCommandService(new CourierMarkArrivedTransport('https://api.example.test', { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(32) }) } as never, async (_input, init) => { retryKeys.push((init?.headers as Record<string, string>)['Idempotency-Key']); return ++calls === 1 ? new Response('', { status: 401 }) : new Response(JSON.stringify(result()), { status: 200 }); }), async () => pickup('travelling_to_merchant', 5), () => scope());
  assert.equal((await healthy.submit(attempt)).state, 'arrived_at_merchant'); assert.deepEqual(retryKeys, [keyA, keyA]);
});

test('strict immediate result accepts only the exact ARRIVED transition and timestamp contract', () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  assert.deepEqual(parseMarkArrivedResult(result(), attempt), { pickupId: pickupA, state: 'arrived_at_merchant', version: 6, travellingAt: '2026-08-08T01:05:00Z', arrivedAt: '2026-08-08T01:10:00Z', updatedAt: '2026-08-08T01:10:00Z' });
  const malformed = [
    result({ pickup_id: pickupB }), result({ state: 'travelling_to_merchant' }), result({ version: 7 }), result({ travelling_at: null }), result({ arrived_at: null }),
    result({ arrived_at: '2026-08-08T01:04:00Z' }), result({ updated_at: '2026-08-08T01:09:00Z' }), result({ merchant_acknowledged_at: '2026-08-08T01:11:00Z' }),
    result({ waiting_duration_seconds: 0 }), result({ terminal_reason: 'other_review_required' }), { ...result(), extra: true },
  ];
  for (const value of malformed) assert.throws(() => parseMarkArrivedResult(value, attempt), MarkArrivedContractError);
});

test('ambiguous transport preserves the sole attempt and key without automatic retry', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA); const keys: string[] = [];
  const service = new CourierMarkArrivedCommandService({ post: async (value) => { keys.push(value.idempotencyKey); throw new PublicApiError('temporarily_unavailable', 503); } }, async () => pickup('travelling_to_merchant', 5), () => scope());
  await assert.rejects(service.submit(attempt), MarkArrivedOutcomeUnknownError); assert.deepEqual(keys, [keyA]);
});

test('known 409s are bounded and an unknown 409 is definitive infrastructure failure, not outcome unknown', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  const cases = new Map([['courier_pickup_version_conflict', 'version_conflict'], ['courier_pickup_transition_not_allowed', 'transition_not_allowed'], ['idempotency_conflict', 'idempotency_conflict'], ['idempotency_replay_unavailable', 'replay_unavailable']]);
  for (const [code, reason] of cases) {
    const transport = new CourierMarkArrivedTransport('https://api.example.test', { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) }) } as never, async () => new Response(JSON.stringify({ detail: { code } }), { status: 409 }));
    await assert.rejects(transport.post(attempt, () => true), (error: unknown) => error instanceof MarkArrivedRejectedError && error.reason === reason);
  }
  const transport = new CourierMarkArrivedTransport('https://api.example.test', { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) }) } as never, async () => new Response(JSON.stringify({ detail: { code: 'new_conflict' } }), { status: 409 }));
  await assert.rejects(transport.post(attempt, () => true), (error: unknown) => error instanceof PublicApiError && error.status === 409);
});

test('reconciliation retries only the exact unchanged travelling attempt', () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  assert.equal(reconcileMarkArrivedRead(pickup('travelling_to_merchant', 5), attempt).outcome, 'retry_same_attempt');
  for (const value of [pickup('travelling_to_merchant', 7), pickup('travelling_to_merchant', 5, { presentation_action: 'none' }), pickup('travelling_to_merchant', 5, { pickup_id: pickupB })]) {
    if ((value as Record<string, unknown>).presentation_action === 'none') assert.throws(() => reconcileMarkArrivedRead(value, attempt), MarkArrivedContractError);
    else assert.deepEqual(reconcileMarkArrivedRead(value, attempt), { outcome: 'invalidated', reason: 'state_changed' });
  }
});

test('ARRIVED and downstream WAITING prove arrival while corrected-back and ENDED remain invalidated', () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  assert.equal(reconcileMarkArrivedRead(pickup('arrived_at_merchant', 6), attempt).outcome, 'already_applied');
  assert.equal(reconcileMarkArrivedRead(pickup('arrived_at_merchant', 8), attempt).outcome, 'already_applied');
  assert.equal(reconcileMarkArrivedRead(pickup('waiting_for_pickup', 7), attempt).outcome, 'already_applied');
  assert.deepEqual(reconcileMarkArrivedRead(pickup('travelling_to_merchant', 7), attempt), { outcome: 'invalidated', reason: 'state_changed' });
  assert.deepEqual(reconcileMarkArrivedRead(pickup('pickup_attempt_ended_before_custody', 6), attempt), { outcome: 'invalidated', reason: 'state_changed' });
});

test('reconciliation maps authority loss, detects scope races, and bounds malformed reads', async () => {
  const attempt = createMarkArrivedAttempt(scope(), () => keyA);
  for (const status of [403, 404]) {
    const service = new CourierMarkArrivedCommandService({ post: async () => result() }, async () => { throw new PublicApiError('not_found', status); }, () => scope());
    assert.deepEqual(await service.reconcile(attempt), { outcome: 'invalidated', reason: 'authority_lost' });
  }
  const stale = new CourierMarkArrivedCommandService({ post: async () => result() }, async () => pickup('arrived_at_merchant', 6), () => undefined);
  assert.deepEqual(await stale.reconcile(attempt), { outcome: 'invalidated', reason: 'authority_lost' });
  let current: MarkArrivedCommandScope | undefined = scope(); let resolve!: (value: unknown) => void;
  const racing = new CourierMarkArrivedCommandService({ post: async () => result() }, () => new Promise((done) => { resolve = done; }), () => current);
  const pending = racing.reconcile(attempt); current = undefined; resolve(pickup('arrived_at_merchant', 6));
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'authority_lost' });
  assert.throws(() => reconcileMarkArrivedRead({ malformed: true }, attempt), MarkArrivedContractError);
});
