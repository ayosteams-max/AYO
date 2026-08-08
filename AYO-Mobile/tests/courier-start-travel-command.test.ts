import assert from 'node:assert/strict';
import test from 'node:test';

import { createStartTravelAttempt, parseStartTravelResult, StartTravelAttemptInvalidError, StartTravelContractError, StartTravelOutcomeUnknownError, StartTravelRejectedError, type CourierCommandScope } from '../domain/courier-start-travel-command.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { CourierStartTravelCommandService, CourierStartTravelTransport } from '../services/courier-start-travel-command.ts';

const identityA = '11111111-1111-4111-8111-111111111111';
const identityB = '22222222-2222-4222-8222-222222222222';
const sessionA = '33333333-3333-4333-8333-333333333333';
const pickupA = '44444444-4444-4444-8444-444444444444';
const pickupB = '55555555-5555-4555-8555-555555555555';
const keyA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const keyB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const scope = (overrides: Partial<CourierCommandScope> = {}): CourierCommandScope => ({ identityId: identityA, sessionId: sessionA, identityGeneration: 7, contextGeneration: 9, pickupId: pickupA, pickupVersion: 4, presentationAction: 'start_travel', ...overrides });
const result = (overrides: Record<string, unknown> = {}) => ({ pickup_id: pickupA, state: 'travelling_to_merchant', version: 5, assigned_at: '2026-08-07T01:00:00Z', travelling_at: '2026-08-07T01:01:00Z', arrived_at: null, merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: '2026-08-07T01:01:00Z', ...overrides });
const pickup = (state: 'courier_assigned' | 'travelling_to_merchant', version: number) => ({ pickup_id: pickupA, state, version, assigned_at: '2026-08-07T01:00:00Z', travelling_at: state === 'travelling_to_merchant' ? '2026-08-07T01:01:00Z' : null, arrived_at: null, merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: state === 'travelling_to_merchant' ? '2026-08-07T01:01:00Z' : '2026-08-07T01:00:00Z', presentation_action: state === 'courier_assigned' ? 'start_travel' : 'mark_arrived' });

test('context change while session restore is pending prevents network dispatch', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); let current = scope(); let resolveRestore!: (value: unknown) => void; let posts = 0;
  const sessions = { restore: () => new Promise((resolve) => { resolveRestore = resolve; }), forceRefresh: async () => undefined } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => { posts += 1; return new Response(JSON.stringify(result()), { status: 200, headers: { 'Content-Type': 'application/json' } }); });
  const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => current);
  const pending = service.submit(attempt); await Promise.resolve(); current = scope({ contextGeneration: 10 });
  resolveRestore({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) });
  await assert.rejects(pending, StartTravelAttemptInvalidError); assert.equal(posts, 0);
});

test('sign-out and identity generation change while restore is pending prevent dispatch', async () => {
  for (const next of [undefined, scope({ identityGeneration: 8 })]) {
    const attempt = createStartTravelAttempt(scope(), () => keyA); let current: CourierCommandScope | undefined = scope(); let resolveRestore!: (value: unknown) => void; let posts = 0;
    const sessions = { restore: () => new Promise((resolve) => { resolveRestore = resolve; }), forceRefresh: async () => undefined } as never;
    const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => { posts += 1; return new Response(JSON.stringify(result()), { status: 200 }); });
    const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => current);
    const pending = service.submit(attempt); await Promise.resolve(); current = next;
    resolveRestore({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) });
    await assert.rejects(pending, StartTravelAttemptInvalidError); assert.equal(posts, 0);
  }
});

test('scope change during token refresh prevents a second dispatch', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); let current = scope(); let resolveRefresh!: (value: unknown) => void; const keys: string[] = [];
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: () => new Promise((resolve) => { resolveRefresh = resolve; }) } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async (_input, init) => { keys.push((init?.headers as Record<string, string>)['Idempotency-Key']); return new Response('', { status: 401 }); });
  const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => current);
  const pending = service.submit(attempt); while (!resolveRefresh) await Promise.resolve(); current = scope({ contextGeneration: 10 });
  resolveRefresh({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(32) });
  await assert.rejects(pending, StartTravelAttemptInvalidError); assert.deepEqual(keys, [keyA]);
});

test('current scope permits one refreshed-token retry with the same key', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); const keys: string[] = []; let calls = 0;
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(32) }) } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async (_input, init) => { keys.push((init?.headers as Record<string, string>)['Idempotency-Key']); return ++calls === 1 ? new Response('', { status: 401 }) : new Response(JSON.stringify(result()), { status: 200 }); });
  const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => scope());
  assert.equal((await service.submit(attempt)).state, 'travelling_to_merchant'); assert.deepEqual(keys, [keyA, keyA]);
});

test('already-aborted signal is invalid before dispatch while in-flight uncertainty remains unknown', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); const controller = new AbortController(); controller.abort(); let posts = 0;
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: async () => undefined } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => { posts += 1; throw new Error('network'); });
  const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => scope());
  await assert.rejects(service.submit(attempt, controller.signal), StartTravelAttemptInvalidError); assert.equal(posts, 0);
  const uncertain = new CourierStartTravelCommandService({ post: async () => { throw new PublicApiError('temporarily_unavailable'); } }, async () => pickup('courier_assigned', 4), () => scope());
  await assert.rejects(uncertain.submit(attempt), StartTravelOutcomeUnknownError);
});

test('abort during restore or refresh prevents the next not-yet-issued dispatch', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA);
  {
    const controller = new AbortController(); let resolveRestore!: (value: unknown) => void; let posts = 0;
    const sessions = { restore: () => new Promise((resolve) => { resolveRestore = resolve; }), forceRefresh: async () => undefined } as never;
    const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => { posts += 1; return new Response(JSON.stringify(result()), { status: 200 }); });
    const pending = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => scope()).submit(attempt, controller.signal);
    await Promise.resolve(); controller.abort(); resolveRestore({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) });
    await assert.rejects(pending, StartTravelAttemptInvalidError); assert.equal(posts, 0);
  }
  {
    const controller = new AbortController(); let resolveRefresh!: (value: unknown) => void; let posts = 0;
    const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(32) }), forceRefresh: () => new Promise((resolve) => { resolveRefresh = resolve; }) } as never;
    const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => { posts += 1; return new Response('', { status: 401 }); });
    const pending = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => scope()).submit(attempt, controller.signal);
    while (!resolveRefresh) await Promise.resolve(); controller.abort(); resolveRefresh({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(32) });
    await assert.rejects(pending, StartTravelAttemptInvalidError); assert.equal(posts, 1);
  }
});

test('secure command attempt is opaque, bounded, immutable, and each new intent is distinct', () => {
  const first = createStartTravelAttempt(scope(), () => keyA); const second = createStartTravelAttempt(scope(), () => keyB);
  assert.equal(first.idempotencyKey.length, 36); assert.notEqual(first.idempotencyKey, second.idempotencyKey);
  assert.equal(first.idempotencyKey.includes(identityA), false); assert.equal(first.idempotencyKey.includes(pickupA), false); assert.equal(Object.isFrozen(first), true);
  assert.throws(() => createStartTravelAttempt(scope(), () => 'weak'), StartTravelAttemptInvalidError);
});

test('attempt binding rejects pickup, version, session, identity, and context changes before transport', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA);
  for (const changed of [scope({ pickupId: pickupB }), scope({ pickupVersion: 5 }), scope({ identityId: identityB }), scope({ sessionId: keyB }), scope({ identityGeneration: 8 }), scope({ contextGeneration: 10 })]) {
    let called = false; const service = new CourierStartTravelCommandService({ post: async () => { called = true; return result(); } }, async () => pickup('courier_assigned', 4), () => changed);
    await assert.rejects(service.submit(attempt), StartTravelAttemptInvalidError); assert.equal(called, false);
  }
});

test('ambiguous failure and retry preserve exactly one idempotency key', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); const keys: string[] = []; let calls = 0;
  const service = new CourierStartTravelCommandService({ post: async (value) => { keys.push(value.idempotencyKey); if (++calls === 1) throw new PublicApiError('temporarily_unavailable', 503); return result(); } }, async () => pickup('courier_assigned', 4), () => scope());
  await assert.rejects(service.submit(attempt), StartTravelOutcomeUnknownError);
  assert.deepEqual(await service.submit(attempt), { pickupId: pickupA, state: 'travelling_to_merchant', version: 5, travellingAt: '2026-08-07T01:01:00Z', updatedAt: '2026-08-07T01:01:00Z' });
  assert.deepEqual(keys, [keyA, keyA]);
});

test('late success cannot publish after sign-out or identity change', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); let current: CourierCommandScope | undefined = scope(); let resolve!: (value: unknown) => void;
  const service = new CourierStartTravelCommandService({ post: () => new Promise((done) => { resolve = done; }) }, async () => pickup('courier_assigned', 4), () => current);
  const pending = service.submit(attempt); current = undefined; resolve(result()); await assert.rejects(pending, StartTravelAttemptInvalidError);
  current = scope({ identityId: identityB, identityGeneration: 8 }); await assert.rejects(service.submit(attempt), StartTravelAttemptInvalidError);
});

test('strict result parser accepts only the exact transition bound to the attempt', () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); assert.equal(parseStartTravelResult(result(), attempt).state, 'travelling_to_merchant');
  for (const malformed of [result({ pickup_id: pickupB }), result({ state: 'courier_assigned' }), result({ version: 6 }), result({ travelling_at: null }), result({ arrived_at: '2026-08-07T01:02:00Z' })]) assert.throws(() => parseStartTravelResult(malformed, attempt), StartTravelContractError);
});

test('reconciliation distinguishes applied, same-key retry, authority loss, and newer conflict', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); let response: unknown = pickup('travelling_to_merchant', 5);
  const service = new CourierStartTravelCommandService({ post: async () => result() }, async () => { if (response instanceof Error) throw response; return response; }, () => scope());
  assert.equal((await service.reconcile(attempt)).outcome, 'already_applied');
  response = pickup('courier_assigned', 4); assert.equal((await service.reconcile(attempt)).outcome, 'retry_same_attempt');
  response = pickup('travelling_to_merchant', 7); assert.deepEqual(await service.reconcile(attempt), { outcome: 'invalidated', reason: 'state_changed' });
  response = new PublicApiError('not_found', 404); assert.deepEqual(await service.reconcile(attempt), { outcome: 'invalidated', reason: 'authority_lost' });
});

test('authenticated transport sends the minimal canonical request and stable key', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA); let captured: [string, RequestInit] | undefined;
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) }), forceRefresh: async () => undefined } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async (input, init) => { captured = [String(input), init ?? {}]; return new Response(JSON.stringify(result()), { status: 200, headers: { 'Content-Type': 'application/json' } }); });
  await transport.post(attempt, () => true); assert.equal(captured?.[0], `https://api.example.test/mobile/courier-pickups/${pickupA}/actions`);
  assert.equal((captured?.[1].headers as Record<string, string>)['Idempotency-Key'], keyA);
  assert.deepEqual(JSON.parse(String(captured?.[1].body)), { expected_version: 4, action: 'start_travel' });
});

test('definitive 409 is not misclassified as an ambiguous transport outcome', async () => {
  const attempt = createStartTravelAttempt(scope(), () => keyA);
  const sessions = { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 't'.repeat(32) }), forceRefresh: async () => undefined } as never;
  const transport = new CourierStartTravelTransport('https://api.example.test', sessions, async () => new Response(JSON.stringify({ detail: { code: 'courier_pickup_version_conflict' } }), { status: 409, headers: { 'Content-Type': 'application/json' } }));
  const service = new CourierStartTravelCommandService(transport, async () => pickup('courier_assigned', 4), () => scope());
  await assert.rejects(service.submit(attempt), (error: unknown) => error instanceof StartTravelRejectedError && error.reason === 'version_conflict');
});
