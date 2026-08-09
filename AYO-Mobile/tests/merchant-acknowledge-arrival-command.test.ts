import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createMerchantAcknowledgeArrivalAttempt,
  MerchantAcknowledgeArrivalAttemptInvalidError,
  MerchantAcknowledgeArrivalContractError,
  MerchantAcknowledgeArrivalOutcomeUnknownError,
  MerchantAcknowledgeArrivalRejectedError,
  parseMerchantAcknowledgeArrivalResult,
  reconcileMerchantAcknowledgeArrivalRead,
  type MerchantAcknowledgeArrivalCommandScope,
} from '../domain/merchant-acknowledge-arrival-command.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import {
  MerchantAcknowledgeArrivalCommandService,
  MerchantAcknowledgeArrivalTransport,
} from '../services/merchant-acknowledge-arrival-command.ts';

const identityA = '11111111-1111-4111-8111-111111111111';
const identityB = '22222222-2222-4222-8222-222222222222';
const sessionA = '33333333-3333-4333-8333-333333333333';
const sessionB = '44444444-4444-4444-8444-444444444444';
const merchantA = '55555555-5555-4555-8555-555555555555';
const merchantB = '66666666-6666-4666-8666-666666666666';
const orderA = '77777777-7777-4777-8777-777777777777';
const orderB = '88888888-8888-4888-8888-888888888888';
const pickupA = '99999999-9999-4999-8999-999999999999';
const pickupB = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const keyA = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const keyB = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

const scope = (overrides: Partial<MerchantAcknowledgeArrivalCommandScope> = {}): MerchantAcknowledgeArrivalCommandScope => ({
  identityId: identityA,
  sessionId: sessionA,
  identityGeneration: 7,
  contextGeneration: 9,
  merchantId: merchantA,
  orderId: orderA,
  pickupId: pickupA,
  pickupVersion: 5,
  presentationAction: 'acknowledge_arrival',
  ...overrides,
});

const commandResult = (overrides: Record<string, unknown> = {}) => ({
  pickup_id: pickupA,
  state: 'waiting_for_pickup',
  version: 6,
  arrived_at: '2026-08-08T01:10:00Z',
  merchant_acknowledged_at: '2026-08-08T01:12:00Z',
  waiting_duration_seconds: 120,
  terminal_reason: null,
  updated_at: '2026-08-08T01:12:00Z',
  ...overrides,
});

function pickupStatus(
  state: 'courier_assigned' | 'travelling_to_merchant' | 'arrived_at_merchant' | 'waiting_for_pickup' | 'pickup_attempt_ended_before_custody',
  version: number,
  overrides: Record<string, unknown> = {},
) {
  const arrived = state === 'arrived_at_merchant' || state === 'waiting_for_pickup';
  const waiting = state === 'waiting_for_pickup';
  return {
    pickup_id: pickupA,
    state,
    version,
    arrived_at: arrived ? '2026-08-08T01:10:00Z' : null,
    merchant_acknowledged_at: waiting ? '2026-08-08T01:12:00Z' : null,
    waiting_duration_seconds: waiting ? 120 : null,
    terminal_reason: state === 'pickup_attempt_ended_before_custody' ? 'courier_unable_to_continue' : null,
    updated_at: waiting ? '2026-08-08T01:12:00Z' : arrived ? '2026-08-08T01:10:00Z' : '2026-08-08T01:05:00Z',
    presentation_action: state === 'arrived_at_merchant' ? 'acknowledge_arrival' : 'none',
    ...overrides,
  };
}

function snapshotFrom(value: ReturnType<typeof pickupStatus>) {
  return {
    pickupId: String(value.pickup_id),
    state: value.state,
    version: value.version,
    arrivedAt: value.arrived_at === null ? undefined : String(value.arrived_at),
    merchantAcknowledgedAt: value.merchant_acknowledged_at === null ? undefined : String(value.merchant_acknowledged_at),
    waitingDurationSeconds: value.waiting_duration_seconds === null ? undefined : Number(value.waiting_duration_seconds),
    terminalReason: value.terminal_reason === null ? undefined : value.terminal_reason,
    updatedAt: String(value.updated_at),
    presentationAction: value.presentation_action,
  } as never;
}

test('one intent creates one immutable ACK-only attempt and one secure key', () => {
  const generated = createMerchantAcknowledgeArrivalAttempt(scope());
  const first = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  const second = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyB);
  assert.match(generated.idempotencyKey, /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.deepEqual(first, {
    action: 'acknowledge_arrival', identityId: identityA, sessionId: sessionA, identityGeneration: 7, contextGeneration: 9, merchantId: merchantA,
    orderId: orderA, pickupId: pickupA, expectedVersion: 5, idempotencyKey: keyA,
  });
  assert.equal(Object.isFrozen(first), true);
  assert.notEqual(first.idempotencyKey, second.idempotencyKey);
  assert.throws(() => createMerchantAcknowledgeArrivalAttempt(scope(), () => 'weak'), MerchantAcknowledgeArrivalAttemptInvalidError);
  for (const invalid of [
    scope({ identityId: 'bad' }), scope({ sessionId: 'bad' }), scope({ merchantId: 'bad' }),
    scope({ identityGeneration: -1 }), scope({ contextGeneration: -1 }), scope({ orderId: 'bad' }),
    scope({ pickupId: 'bad' }), scope({ pickupVersion: 0 }),
    { ...scope(), presentationAction: 'none' },
  ]) assert.throws(() => createMerchantAcknowledgeArrivalAttempt(invalid as MerchantAcknowledgeArrivalCommandScope, () => keyA), MerchantAcknowledgeArrivalAttemptInvalidError);
});

test('every bound identity, session, generation, context, merchant, order, Pickup, version, or action change prevents POST', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  const changed = [
    scope({ identityId: identityB }), scope({ sessionId: sessionB }), scope({ identityGeneration: 8 }),
    scope({ contextGeneration: 10 }), scope({ merchantId: merchantB }),
    scope({ orderId: orderB }), scope({ pickupId: pickupB }), scope({ pickupVersion: 6 }),
    { ...scope(), presentationAction: 'none' } as unknown as MerchantAcknowledgeArrivalCommandScope,
  ];
  for (const current of changed) {
    let posts = 0;
    const service = new MerchantAcknowledgeArrivalCommandService(
      { post: async () => { posts += 1; return commandResult(); } },
      { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
      () => current,
    );
    await assert.rejects(service.submit(attempt), MerchantAcknowledgeArrivalAttemptInvalidError);
    assert.equal(posts, 0);
  }
});

test('transport uses canonical session and the exact ACK endpoint, headers, and body', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  let captured: [string, RequestInit] | undefined;
  const sessions = {
    restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }),
    forceRefresh: async () => undefined,
  } as never;
  const transport = new MerchantAcknowledgeArrivalTransport('https://api.example.test', sessions, async (input, init) => {
    captured = [String(input), init ?? {}];
    return new Response(JSON.stringify(commandResult()), { status: 200 });
  });
  await transport.post(attempt, () => true);
  assert.equal(captured?.[0], `https://api.example.test/mobile/merchants/${merchantA}/courier-pickups/${pickupA}/acknowledge`);
  assert.equal(captured?.[1].method, 'POST');
  assert.deepEqual(captured?.[1].headers, {
    Accept: 'application/json', Authorization: `Bearer ${'a'.repeat(64)}`, 'Content-Type': 'application/json', 'Idempotency-Key': keyA,
  });
  assert.deepEqual(JSON.parse(String(captured?.[1].body)), { expected_version: 5, action: 'acknowledge_arrival' });
  assert.ok(!String(captured?.[1].body).includes('reason'));
  assert.ok(!String(captured?.[1].body).includes('location'));
});

test('identity/session failure and currentness loss during restore prevent dispatch', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  let blockedPosts = 0;
  const blocked = new MerchantAcknowledgeArrivalTransport('https://api.example.test', {} as never, async () => { blockedPosts += 1; return new Response(); });
  await assert.rejects(blocked.post(attempt, () => false), MerchantAcknowledgeArrivalAttemptInvalidError);
  assert.equal(blockedPosts, 0);
  for (const restored of [
    undefined,
    { identityId: identityB, sessionId: sessionA, accessToken: 'a'.repeat(64) },
    { identityId: identityA, sessionId: sessionB, accessToken: 'a'.repeat(64) },
  ]) {
    let posts = 0;
    const transport = new MerchantAcknowledgeArrivalTransport('https://api.example.test', { restore: async () => restored } as never, async () => { posts += 1; return new Response(); });
    await assert.rejects(transport.post(attempt, () => true), MerchantAcknowledgeArrivalAttemptInvalidError);
    assert.equal(posts, 0);
  }

  let current: MerchantAcknowledgeArrivalCommandScope | undefined = scope();
  let resolveRestore!: (value: unknown) => void;
  let posts = 0;
  const transport = new MerchantAcknowledgeArrivalTransport(
    'https://api.example.test',
    { restore: () => new Promise((resolve) => { resolveRestore = resolve; }) } as never,
    async () => { posts += 1; return new Response(JSON.stringify(commandResult()), { status: 200 }); },
  );
  const service = new MerchantAcknowledgeArrivalCommandService(transport, { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) }, () => current);
  const pending = service.submit(attempt);
  await Promise.resolve();
  current = undefined;
  resolveRestore({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) });
  await assert.rejects(pending, MerchantAcknowledgeArrivalAttemptInvalidError);
  assert.equal(posts, 0);
});

test('successful POST cannot complete into a retired or replacement trusted scope', async () => {
  for (const replacement of [undefined, scope({ contextGeneration: 10 })]) {
    let current: MerchantAcknowledgeArrivalCommandScope | undefined = scope();
    let resolvePost!: (value: unknown) => void;
    let posts = 0;
    let reads = 0;
    let keysCreated = 0;
    const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => { keysCreated += 1; return keyA; });
    const keys: string[] = [];
    const service = new MerchantAcknowledgeArrivalCommandService(
      {
        post: async (value) => {
          posts += 1;
          keys.push(value.idempotencyKey);
          return new Promise((resolve) => { resolvePost = resolve; });
        },
      },
      { load: async () => { reads += 1; return snapshotFrom(pickupStatus('arrived_at_merchant', 5)); } },
      () => current,
    );

    const pending = service.submit(attempt);
    while (!resolvePost) await Promise.resolve();
    current = replacement;
    resolvePost(commandResult());

    await assert.rejects(pending, MerchantAcknowledgeArrivalAttemptInvalidError);
    assert.equal(posts, 1);
    assert.deepEqual(keys, [keyA]);
    assert.equal(keysCreated, 1);
    assert.equal(reads, 0);
  }
});

test('401 refresh preserves the exact attempt and key and rechecks currentness', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  let current: MerchantAcknowledgeArrivalCommandScope | undefined = scope();
  let resolveRefresh!: (value: unknown) => void;
  const keys: string[] = [];
  const transport = new MerchantAcknowledgeArrivalTransport(
    'https://api.example.test',
    {
      restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }),
      forceRefresh: () => new Promise((resolve) => { resolveRefresh = resolve; }),
    } as never,
    async (_input, init) => { keys.push((init?.headers as Record<string, string>)['Idempotency-Key']); return new Response('', { status: 401 }); },
  );
  const service = new MerchantAcknowledgeArrivalCommandService(transport, { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) }, () => current);
  const pending = service.submit(attempt);
  while (!resolveRefresh) await Promise.resolve();
  current = undefined;
  resolveRefresh({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(64) });
  await assert.rejects(pending, MerchantAcknowledgeArrivalAttemptInvalidError);
  assert.deepEqual(keys, [keyA]);

  let sends = 0;
  const sent: Array<{ key: string; body: string }> = [];
  const healthy = new MerchantAcknowledgeArrivalCommandService(
    new MerchantAcknowledgeArrivalTransport(
      'https://api.example.test',
      {
        restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }),
        forceRefresh: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(64) }),
      } as never,
      async (_input, init) => {
        sent.push({ key: (init?.headers as Record<string, string>)['Idempotency-Key'], body: String(init?.body) });
        return ++sends === 1 ? new Response('', { status: 401 }) : new Response(JSON.stringify(commandResult()), { status: 200 });
      },
    ),
    { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
    () => scope(),
  );
  assert.equal((await healthy.submit(attempt)).state, 'waiting_for_pickup');
  assert.deepEqual(sent, [
    { key: keyA, body: JSON.stringify({ expected_version: 5, action: 'acknowledge_arrival' }) },
    { key: keyA, body: JSON.stringify({ expected_version: 5, action: 'acknowledge_arrival' }) },
  ]);

  let postRefreshCurrent: MerchantAcknowledgeArrivalCommandScope | undefined = scope();
  let resolveSecond!: (value: Response) => void;
  const postRefreshKeys: string[] = [];
  const postRefresh = new MerchantAcknowledgeArrivalCommandService(
    new MerchantAcknowledgeArrivalTransport(
      'https://api.example.test',
      {
        restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }),
        forceRefresh: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'b'.repeat(64) }),
      } as never,
      async (_input, init) => {
        postRefreshKeys.push((init?.headers as Record<string, string>)['Idempotency-Key']);
        if (postRefreshKeys.length === 1) return new Response('', { status: 401 });
        return new Promise((resolve) => { resolveSecond = resolve; });
      },
    ),
    { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
    () => postRefreshCurrent,
  );
  const postRefreshPending = postRefresh.submit(attempt);
  while (!resolveSecond) await Promise.resolve();
  postRefreshCurrent = undefined;
  resolveSecond(new Response(JSON.stringify(commandResult()), { status: 200 }));
  await assert.rejects(postRefreshPending, MerchantAcknowledgeArrivalAttemptInvalidError);
  assert.deepEqual(postRefreshKeys, [keyA, keyA]);
});

test('strict success parser accepts only the exact WAITING transition contract', () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  assert.deepEqual(parseMerchantAcknowledgeArrivalResult(commandResult(), attempt), {
    pickupId: pickupA, state: 'waiting_for_pickup', version: 6, arrivedAt: '2026-08-08T01:10:00Z',
    merchantAcknowledgedAt: '2026-08-08T01:12:00Z', waitingDurationSeconds: 120, updatedAt: '2026-08-08T01:12:00Z',
  });
  const malformed = [
    commandResult({ pickup_id: pickupB }), commandResult({ state: 'arrived_at_merchant' }), commandResult({ version: 7 }),
    commandResult({ arrived_at: null }), commandResult({ merchant_acknowledged_at: null }), commandResult({ waiting_duration_seconds: -1 }),
    commandResult({ waiting_duration_seconds: 1.5 }), commandResult({ terminal_reason: 'other_review_required' }),
    commandResult({ merchant_acknowledged_at: '2026-08-08T01:09:00Z' }), commandResult({ updated_at: '2026-08-08T01:11:00Z' }),
    { ...commandResult(), extra: true },
    (({ updated_at: _removed, ...missing }) => missing)(commandResult()),
  ];
  for (const value of malformed) assert.throws(() => parseMerchantAcknowledgeArrivalResult(value, attempt), MerchantAcknowledgeArrivalContractError);
});

test('network, 5xx, cancellation, and malformed 2xx are outcome unknown with no automatic resend', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  for (const error of [
    new PublicApiError('temporarily_unavailable'),
    new PublicApiError('temporarily_unavailable', 503),
    new PublicApiError('request_cancelled'),
    new PublicApiError('malformed_response', 200),
  ]) {
    const keys: string[] = [];
    const service = new MerchantAcknowledgeArrivalCommandService(
      { post: async (value) => { keys.push(value.idempotencyKey); throw error; } },
      { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
      () => scope(),
    );
    await assert.rejects(service.submit(attempt), MerchantAcknowledgeArrivalOutcomeUnknownError);
    assert.deepEqual(keys, [keyA]);
  }
  const malformed = new MerchantAcknowledgeArrivalCommandService(
    { post: async () => commandResult({ state: 'arrived_at_merchant' }) },
    { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
    () => scope(),
  );
  await assert.rejects(malformed.submit(attempt), MerchantAcknowledgeArrivalOutcomeUnknownError);
});

test('known merchant ACK 409s are exact and unknown 409 grants no retry authority', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  const cases = new Map([
    ['courier_pickup_version_conflict', 'version_conflict'],
    ['courier_pickup_transition_not_allowed', 'transition_not_allowed'],
    ['idempotency_conflict', 'idempotency_conflict'],
    ['idempotency_replay_unavailable', 'replay_unavailable'],
    ['courier_pickup_temporarily_unavailable', 'temporarily_unavailable'],
  ]);
  for (const [code, reason] of cases) {
    const transport = new MerchantAcknowledgeArrivalTransport(
      'https://api.example.test',
      { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }) } as never,
      async () => new Response(JSON.stringify({ error: { code } }), { status: 409 }),
    );
    await assert.rejects(transport.post(attempt, () => true), (error: unknown) => error instanceof MerchantAcknowledgeArrivalRejectedError && error.reason === reason);
  }
  const unknown = new MerchantAcknowledgeArrivalTransport(
    'https://api.example.test',
    { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }) } as never,
    async () => new Response(JSON.stringify({ error: { code: 'future_conflict' } }), { status: 409 }),
  );
  await assert.rejects(unknown.post(attempt, () => true), (error: unknown) => error instanceof PublicApiError && error.status === 409);
});

test('approval loss after positive evidence is a definitive bounded denial with the original key', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  const keys: string[] = [];
  let posts = 0;
  const transport = new MerchantAcknowledgeArrivalTransport(
    'https://api.example.test',
    { restore: async () => ({ identityId: identityA, sessionId: sessionA, accessToken: 'a'.repeat(64) }) } as never,
    async (_input, init) => {
      posts += 1;
      keys.push((init?.headers as Record<string, string>)['Idempotency-Key']);
      return new Response(JSON.stringify({ error: { code: 'courier_pickup_temporarily_unavailable' } }), { status: 409 });
    },
  );
  const service = new MerchantAcknowledgeArrivalCommandService(
    transport,
    { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
    () => scope(),
  );

  await assert.rejects(
    service.submit(attempt),
    (error: unknown) => error instanceof MerchantAcknowledgeArrivalRejectedError && error.reason === 'temporarily_unavailable',
  );
  assert.equal(posts, 1);
  assert.deepEqual(keys, [keyA]);
});

test('reconciliation retries only exact unchanged ARRIVED with positive server evidence', () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  assert.equal(reconcileMerchantAcknowledgeArrivalRead(pickupStatus('arrived_at_merchant', 5), attempt).outcome, 'retry_same_attempt');
  assert.deepEqual(
    reconcileMerchantAcknowledgeArrivalRead(pickupStatus('arrived_at_merchant', 5, { presentation_action: 'none' }), attempt),
    { outcome: 'invalidated', reason: 'authority_lost' },
  );
  assert.deepEqual(
    reconcileMerchantAcknowledgeArrivalRead(pickupStatus('arrived_at_merchant', 7), attempt),
    { outcome: 'invalidated', reason: 'state_changed' },
  );
});

test('WAITING proves desired acknowledgement state while correction and ending histories stay conservative', () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  assert.equal(reconcileMerchantAcknowledgeArrivalRead(pickupStatus('waiting_for_pickup', 6), attempt).outcome, 'already_applied');
  assert.equal(reconcileMerchantAcknowledgeArrivalRead(pickupStatus('waiting_for_pickup', 8), attempt).outcome, 'already_applied');
  for (const value of [
    pickupStatus('arrived_at_merchant', 7),
    pickupStatus('travelling_to_merchant', 6),
    pickupStatus('pickup_attempt_ended_before_custody', 6),
    pickupStatus('waiting_for_pickup', 6, { pickup_id: pickupB }),
  ]) assert.deepEqual(reconcileMerchantAcknowledgeArrivalRead(value, attempt), { outcome: 'invalidated', reason: 'state_changed' });
  for (const value of [
    pickupStatus('waiting_for_pickup', 6, { merchant_acknowledged_at: null }),
    pickupStatus('waiting_for_pickup', 6, { waiting_duration_seconds: null }),
    pickupStatus('waiting_for_pickup', 6, { merchant_acknowledged_at: '2026-08-08T01:09:00Z' }),
  ]) assert.throws(() => reconcileMerchantAcknowledgeArrivalRead(value, attempt), MerchantAcknowledgeArrivalContractError);
});

test('explicit reconciliation uses one merchant GET, maps authority loss, and never creates a key', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  const calls: Array<[string, string]> = [];
  const service = new MerchantAcknowledgeArrivalCommandService(
    { post: async () => commandResult() },
    { load: async (merchantId, orderId) => { calls.push([merchantId, orderId]); return snapshotFrom(pickupStatus('arrived_at_merchant', 5)); } },
    () => scope(),
  );
  assert.equal((await service.reconcile(attempt)).outcome, 'retry_same_attempt');
  assert.deepEqual(calls, [[merchantA, orderA]]);
  assert.equal(attempt.idempotencyKey, keyA);

  for (const status of [403, 404, 409]) {
    const denied = new MerchantAcknowledgeArrivalCommandService(
      { post: async () => commandResult() },
      { load: async () => { throw new PublicApiError(status === 409 ? 'temporarily_unavailable' : 'not_found', status); } },
      () => scope(),
    );
    assert.deepEqual(await denied.reconcile(attempt), { outcome: 'invalidated', reason: 'authority_lost' });
  }
  const transient = new MerchantAcknowledgeArrivalCommandService(
    { post: async () => commandResult() },
    { load: async () => { throw new PublicApiError('temporarily_unavailable', 503); } },
    () => scope(),
  );
  await assert.rejects(transient.reconcile(attempt), (error: unknown) => error instanceof PublicApiError && error.status === 503);
});

test('reconciliation currentness races fail closed and same-attempt retry preserves the key', async () => {
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  let operationCurrent = true;
  let resolve!: (value: never) => void;
  const racing = new MerchantAcknowledgeArrivalCommandService(
    { post: async () => commandResult() },
    { load: () => new Promise((done) => { resolve = done; }) },
    () => scope(),
    () => operationCurrent,
  );
  const pending = racing.reconcile(attempt);
  operationCurrent = false;
  resolve(snapshotFrom(pickupStatus('arrived_at_merchant', 5)));
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'authority_lost' });

  const keys: string[] = [];
  const retry = new MerchantAcknowledgeArrivalCommandService(
    { post: async (value) => { keys.push(value.idempotencyKey); return commandResult(); } },
    { load: async () => snapshotFrom(pickupStatus('arrived_at_merchant', 5)) },
    () => scope(),
  );
  assert.equal((await retry.reconcile(attempt)).outcome, 'retry_same_attempt');
  await retry.submit(attempt);
  assert.deepEqual(keys, [keyA]);
});

test('construction and attempt creation perform no automatic network, command, or Custody work', () => {
  let posts = 0;
  let reads = 0;
  const service = new MerchantAcknowledgeArrivalCommandService(
    { post: async () => { posts += 1; return commandResult(); } },
    { load: async () => { reads += 1; return snapshotFrom(pickupStatus('arrived_at_merchant', 5)); } },
    () => scope(),
  );
  const attempt = createMerchantAcknowledgeArrivalAttempt(scope(), () => keyA);
  assert.equal(posts, 0);
  assert.equal(reads, 0);
  assert.equal(typeof (service as unknown as Record<string, unknown>).controller, 'undefined');
  assert.equal(typeof (service as unknown as Record<string, unknown>).custody, 'undefined');
  assert.equal(attempt.action, 'acknowledge_arrival');
});
