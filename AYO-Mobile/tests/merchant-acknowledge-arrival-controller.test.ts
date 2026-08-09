import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createMerchantAcknowledgeArrivalAttempt,
  MerchantAcknowledgeArrivalAttemptInvalidError,
  MerchantAcknowledgeArrivalOutcomeUnknownError,
  MerchantAcknowledgeArrivalRejectedError,
  type MerchantAcknowledgeArrivalAttempt,
  type MerchantAcknowledgeArrivalReconciliation,
  type MerchantAcknowledgeArrivalResult,
} from '../domain/merchant-acknowledge-arrival-command.ts';
import type { MerchantCourierPickupSnapshot } from '../domain/merchant-courier-pickup-status.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { MerchantAcknowledgeArrivalCommandScope } from '../services/merchant-acknowledge-arrival-command-scope.ts';
import { MerchantAcknowledgeArrivalController } from '../services/merchant-acknowledge-arrival-controller.ts';
import type { MerchantAcknowledgeArrivalDispatchObserver } from '../services/merchant-acknowledge-arrival-command.ts';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const merchantId = '33333333-3333-4333-8333-333333333333';
const orderId = '44444444-4444-4444-8444-444444444444';
const pickupId = '55555555-5555-4555-8555-555555555555';
const otherId = '66666666-6666-4666-8666-666666666666';
const keys = [
  '77777777-7777-4777-8777-777777777777',
  '88888888-8888-4888-8888-888888888888',
];

const arrived = (version = 4, action: 'acknowledge_arrival' | 'none' = 'acknowledge_arrival'): MerchantCourierPickupSnapshot => Object.freeze({
  pickupId,
  state: 'arrived_at_merchant',
  version,
  arrivedAt: '2026-08-09T00:00:00Z',
  updatedAt: '2026-08-09T00:00:00Z',
  presentationAction: action,
});

const waiting = (version = 5): MerchantCourierPickupSnapshot => Object.freeze({
  pickupId,
  state: 'waiting_for_pickup',
  version,
  arrivedAt: '2026-08-09T00:00:00Z',
  merchantAcknowledgedAt: '2026-08-09T00:01:00Z',
  waitingDurationSeconds: 60,
  updatedAt: '2026-08-09T00:01:00Z',
  presentationAction: 'none',
});

const applied: MerchantAcknowledgeArrivalResult = Object.freeze({
  pickupId,
  state: 'waiting_for_pickup',
  version: 5,
  arrivedAt: '2026-08-09T00:00:00Z',
  merchantAcknowledgedAt: '2026-08-09T00:01:00Z',
  waitingDurationSeconds: 60,
  updatedAt: '2026-08-09T00:01:00Z',
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

type Service = {
  submit(
    attempt: MerchantAcknowledgeArrivalAttempt,
    signal?: AbortSignal,
    onDispatch?: MerchantAcknowledgeArrivalDispatchObserver,
  ): Promise<MerchantAcknowledgeArrivalResult>;
  reconcile(attempt: MerchantAcknowledgeArrivalAttempt, signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalReconciliation>;
};

function fixture(overrides: Partial<Service> = {}) {
  let identityGeneration = 1;
  let contextGeneration = 1;
  let currentIdentityId = identityId;
  let currentSessionId = sessionId;
  let currentMerchantId = merchantId;
  let currentOrderId = orderId;
  let currentPickupId = pickupId;
  let continuity = true;
  let creations = 0;
  const submitted: MerchantAcknowledgeArrivalAttempt[] = [];
  const reconciled: MerchantAcknowledgeArrivalAttempt[] = [];
  const scope = new MerchantAcknowledgeArrivalCommandScope(
    () => currentIdentityId ? { identityId: currentIdentityId, sessionId: currentSessionId, identityGeneration } : undefined,
    () => ({
      merchantId: currentMerchantId,
      orderId: currentOrderId,
      pickupId: currentPickupId,
      contextGeneration,
      identityContinuity: Object.freeze({ isCurrent: () => continuity }),
    }),
    (value) => createMerchantAcknowledgeArrivalAttempt(value, () => keys[creations++] ?? keys[1]),
  );
  const service: Service = {
    submit: overrides.submit ?? (async (attempt) => { submitted.push(attempt); return applied; }),
    reconcile: overrides.reconcile ?? (async (attempt) => {
      reconciled.push(attempt);
      return Object.freeze({ outcome: 'retry_same_attempt', pickup: arrived(attempt.expectedVersion) });
    }),
  };
  if (overrides.submit) service.submit = async (attempt, signal, onDispatch) => {
    submitted.push(attempt);
    return overrides.submit!(attempt, signal, onDispatch);
  };
  if (overrides.reconcile) service.reconcile = async (attempt, signal) => { reconciled.push(attempt); return overrides.reconcile!(attempt, signal); };
  const controller = new MerchantAcknowledgeArrivalController(scope, () => service);
  const publish = (pickup = arrived()) => scope.publishFresh(currentMerchantId, currentOrderId, pickup);
  publish();
  return {
    controller, scope, publish, submitted, reconciled,
    creations: () => creations,
    setIdentityGeneration: (value: number) => { identityGeneration = value; },
    setContextGeneration: (value: number) => { contextGeneration = value; },
    setIdentity: (value: string) => { currentIdentityId = value; },
    setSession: (value: string) => { currentSessionId = value; },
    setMerchant: (value: string) => { currentMerchantId = value; },
    setOrder: (value: string) => { currentOrderId = value; },
    setPickup: (value: string) => { currentPickupId = value; },
    setContinuity: (value: boolean) => { continuity = value; },
  };
}

test('construction and pure capability reads create no attempt, key, or network work', () => {
  const value = fixture();
  assert.deepEqual(value.controller.state(), { status: 'idle' });
  assert.equal(Object.isFrozen(value.controller.state()), true);
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), true);
  assert.equal(value.controller.isReconciliationAvailable(), false);
  assert.equal(value.creations(), 0);
  assert.equal(value.submitted.length, 0);
  assert.equal(value.reconciled.length, 0);
});

test('missing or non-actionable evidence fails closed without key creation', async () => {
  for (const evidence of [undefined, arrived(4, 'none')]) {
    const value = fixture();
    value.scope.releaseProviderLifetime();
    value.scope.retainProviderLifetime();
    if (evidence) value.publish(evidence);
    assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
    assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'invalidated', reason: 'scope_changed' });
    assert.equal(value.creations(), 0);
    assert.equal(value.submitted.length, 0);
  }
});

test('identity or session replacement invalidates fresh evidence before attempt creation', async () => {
  for (const replace of [
    (value: ReturnType<typeof fixture>) => value.setIdentity(otherId),
    (value: ReturnType<typeof fixture>) => value.setSession(otherId),
  ]) {
    const value = fixture();
    replace(value);
    assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
    assert.deepEqual(await value.controller.acknowledgeArrival(), {
      outcome: 'invalidated', reason: 'scope_changed',
    });
    assert.equal(value.creations(), 0);
    assert.equal(value.submitted.length, 0);
  }
});

test('one explicit intent creates one frozen exact-scope attempt and one key', async () => {
  const value = fixture();
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  assert.equal(value.creations(), 1);
  assert.equal(value.submitted.length, 1);
  assert.equal(Object.isFrozen(value.submitted[0]), true);
  assert.deepEqual(value.submitted[0], {
    action: 'acknowledge_arrival', identityId, sessionId, identityGeneration: 1, contextGeneration: 1,
    merchantId, orderId, pickupId, expectedVersion: 4, idempotencyKey: keys[0],
  });
});

test('same-tick duplicate intent joins one submit and creates one key', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalResult>();
  const value = fixture({ submit: async () => gate.promise });
  const first = value.controller.acknowledgeArrival();
  const second = value.controller.acknowledgeArrival();
  assert.equal(first, second);
  assert.deepEqual(value.controller.state(), { status: 'submitting' });
  await Promise.resolve();
  assert.equal(value.creations(), 1);
  assert.equal(value.submitted.length, 1);
  gate.resolve(applied);
  assert.deepEqual(await first, { outcome: 'applied' });
});

test('outcome unknown retains custody and suppresses new intent until explicit reconciliation', async () => {
  const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); } });
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'outcome_unknown' });
  assert.deepEqual(value.controller.state(), { status: 'outcome_unknown' });
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.equal(value.controller.isReconciliationAvailable(), true);
  value.publish(arrived(5));
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'outcome_unknown' });
  assert.equal(value.creations(), 1);
  assert.equal(value.submitted.length, 1);
  assert.equal(value.reconciled.length, 0);
});

test('explicit reconciliation is single-flight, creates no key, and retry reuses exact attempt', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalReconciliation>();
  let submits = 0;
  const value = fixture({
    submit: async () => { submits += 1; if (submits === 1) throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); return applied; },
    reconcile: async () => gate.promise,
  });
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'outcome_unknown' });
  const original = value.submitted[0];
  const first = value.controller.reconcileAcknowledgeArrival();
  const second = value.controller.reconcileAcknowledgeArrival();
  assert.equal(first, second);
  assert.deepEqual(value.controller.state(), { status: 'reconciling' });
  await Promise.resolve();
  assert.equal(value.reconciled.length, 1);
  assert.equal(value.creations(), 1);
  gate.resolve(Object.freeze({ outcome: 'retry_same_attempt', pickup: arrived(4) }));
  assert.deepEqual(await first, { outcome: 'retry_same_attempt' });
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  assert.equal(value.submitted.length, 2);
  assert.equal(value.submitted[0], original);
  assert.equal(value.submitted[1], original);
  assert.equal(value.submitted[1].idempotencyKey, keys[0]);
  assert.equal(value.creations(), 1);
});

test('already applied is terminal and fabricates no Custody data', async () => {
  const value = fixture({
    submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); },
    reconcile: async () => Object.freeze({ outcome: 'already_applied', pickup: waiting() }),
  });
  await value.controller.acknowledgeArrival();
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'applied' });
  assert.deepEqual(value.controller.state(), { status: 'applied' });
  assert.deepEqual(Object.keys(value.controller.state()).sort(), ['status']);
  assert.equal(value.controller.isReconciliationAvailable(), false);
});

test('applied version watermark suppresses stale replay but permits a genuinely newer condition', async () => {
  const value = fixture();
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  value.publish(arrived(3));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  value.publish(arrived(7));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), true);
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  assert.equal(value.creations(), 2);
  assert.equal(value.submitted[1].expectedVersion, 7);
  assert.equal(value.submitted[1].idempotencyKey, keys[1]);
});

test('stale submit completion cannot overwrite a replacement operation', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalResult>();
  const value = fixture({ submit: async () => gate.promise });
  const pending = value.controller.acknowledgeArrival();
  value.setContextGeneration(2);
  value.publish(arrived(5));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  gate.resolve(applied);
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });
  assert.deepEqual(value.controller.state(), { status: 'invalidated', reason: 'scope_changed' });
  assert.equal(value.creations(), 1);
});

test('terminal suppression survives same-identity session replacement', async () => {
  const value = fixture();
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  value.setSession(otherId);
  value.setIdentityGeneration(2);
  value.setContextGeneration(2);
  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'applied' });
  assert.equal(value.creations(), 1);
  assert.equal(value.submitted.length, 1);
});

test('stale reconciliation cannot grant retry after scope replacement', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalReconciliation>();
  const value = fixture({
    submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); },
    reconcile: async () => gate.promise,
  });
  await value.controller.acknowledgeArrival();
  const pending = value.controller.reconcileAcknowledgeArrival();
  value.setContextGeneration(2);
  value.publish(arrived(5));
  gate.resolve(Object.freeze({ outcome: 'retry_same_attempt', pickup: arrived(4) }));
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(value.submitted.length, 1);
  assert.equal(value.creations(), 1);
});

test('identity, session, context, merchant, order, Pickup, and continuity changes cannot inherit retry', async () => {
  const changes = [
    (v: ReturnType<typeof fixture>) => v.setIdentity(otherId),
    (v: ReturnType<typeof fixture>) => v.setSession(otherId),
    (v: ReturnType<typeof fixture>) => v.setIdentityGeneration(2),
    (v: ReturnType<typeof fixture>) => v.setContextGeneration(2),
    (v: ReturnType<typeof fixture>) => v.setMerchant(otherId),
    (v: ReturnType<typeof fixture>) => v.setOrder(otherId),
    (v: ReturnType<typeof fixture>) => v.setPickup(otherId),
    (v: ReturnType<typeof fixture>) => v.setContinuity(false),
  ];
  for (const change of changes) {
    const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); } });
    await value.controller.acknowledgeArrival();
    change(value);
    assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
    assert.equal(value.controller.isReconciliationAvailable(), false);
    assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'invalidated', reason: 'scope_changed' });
    assert.equal(value.creations(), 1);
    assert.equal(value.submitted.length, 1);
  }
});

test('provider release/remount preserves ambiguity without recreating a key', async () => {
  const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); } });
  await value.controller.acknowledgeArrival();
  value.scope.releaseProviderLifetime();
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  value.scope.retainProviderLifetime();
  value.publish();
  assert.deepEqual(value.controller.state(), { status: 'outcome_unknown' });
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.equal(value.creations(), 1);
  assert.equal(value.submitted.length, 1);
});

test('scope loss cannot turn an outcome-unknown stale version into a new key', async () => {
  const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); } });
  await value.controller.acknowledgeArrival();
  value.setSession(otherId);
  value.setIdentityGeneration(2);
  value.setContextGeneration(2);
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), {
    outcome: 'invalidated', reason: 'scope_changed',
  });

  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.equal(value.creations(), 1);

  value.publish(arrived(5));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), true);
});

test('retirement is fail-closed and cannot be reversed by remount', async () => {
  const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); } });
  await value.controller.acknowledgeArrival();
  value.scope.retire();
  value.scope.retainProviderLifetime();
  value.publish();
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(value.creations(), 1);
});

test('definitive rejection is bounded and never reconciles or retries automatically', async () => {
  const value = fixture({ submit: async () => { throw new MerchantAcknowledgeArrivalRejectedError('temporarily_unavailable'); } });
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'rejected', reason: 'temporarily_unavailable' });
  assert.deepEqual(value.controller.state(), { status: 'rejected', reason: 'temporarily_unavailable' });
  assert.equal(value.reconciled.length, 0);
  assert.equal(value.submitted.length, 1);
  assert.equal(value.creations(), 1);
});

test('transient reconciliation failure preserves ambiguity for a later explicit GET', async () => {
  let calls = 0;
  const value = fixture({
    submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); },
    reconcile: async () => {
      if (++calls === 1) throw new PublicApiError('temporarily_unavailable', 503);
      return Object.freeze({ outcome: 'already_applied', pickup: waiting() });
    },
  });
  await value.controller.acknowledgeArrival();
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'outcome_unknown' });
  assert.deepEqual(value.controller.state(), { status: 'outcome_unknown' });
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'applied' });
  assert.equal(value.reconciled.length, 2);
  assert.equal(value.creations(), 1);
});

test('authority-loss reconciliation invalidates without new POST or key', async () => {
  const value = fixture({
    submit: async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); },
    reconcile: async () => { throw new PublicApiError('access_denied', 403); },
  });
  await value.controller.acknowledgeArrival();
  assert.deepEqual(await value.controller.reconcileAcknowledgeArrival(), { outcome: 'invalidated', reason: 'authority_lost' });
  assert.equal(value.submitted.length, 1);
  assert.equal(value.reconciled.length, 1);
  assert.equal(value.creations(), 1);
});

test('pre-dispatch attempt invalidation permits fresh same-version recovery with a new explicit intent', async () => {
  const preflight = deferred<void>();
  let dispatches = 0;
  const value = fixture({
    submit: async (_attempt, _signal, _onDispatch) => {
      await preflight.promise;
      throw new MerchantAcknowledgeArrivalAttemptInvalidError();
    },
  });
  const pending = value.controller.acknowledgeArrival();
  while (value.submitted.length === 0) await Promise.resolve();
  value.setContextGeneration(2);
  preflight.resolve();
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(dispatches, 0);
  assert.equal(value.submitted.length, 1);
  assert.equal(value.reconciled.length, 0);
  assert.equal(value.creations(), 1);
  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), true);
  await value.controller.acknowledgeArrival();
  assert.equal(value.submitted.length, 2);
  assert.equal(value.creations(), 2);
  assert.notEqual(value.submitted[0].idempotencyKey, value.submitted[1].idempotencyKey);
});

test('post-dispatch attempt invalidation consumes stale version without replacement key', async () => {
  const response = deferred<void>();
  const value = fixture({
    submit: async (_attempt, _signal, onDispatch) => {
      onDispatch?.();
      await response.promise;
      throw new MerchantAcknowledgeArrivalAttemptInvalidError();
    },
  });
  const pending = value.controller.acknowledgeArrival();
  while (value.submitted.length === 0) await Promise.resolve();
  value.setContextGeneration(2);
  response.resolve();
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });

  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(await value.controller.acknowledgeArrival(), { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(value.submitted.length, 1);
  assert.equal(value.reconciled.length, 0);
  assert.equal(value.creations(), 1);
});

test('first dispatched 401 consumes version when scope retires before second POST', async () => {
  const refresh = deferred<void>();
  const posts: string[] = [];
  const value = fixture({
    submit: async (attempt, _signal, onDispatch) => {
      posts.push(attempt.idempotencyKey);
      onDispatch?.();
      await refresh.promise;
      throw new MerchantAcknowledgeArrivalAttemptInvalidError();
    },
  });
  const pending = value.controller.acknowledgeArrival();
  while (posts.length === 0) await Promise.resolve();
  value.setContextGeneration(2);
  refresh.resolve();
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });
  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(posts, [keys[0]]);
  assert.equal(value.creations(), 1);
});

test('scope loss after second same-key POST consumes version and cannot produce a third POST', async () => {
  const secondResponse = deferred<MerchantAcknowledgeArrivalResult>();
  const posts: string[] = [];
  const value = fixture({
    submit: async (attempt, _signal, onDispatch) => {
      posts.push(attempt.idempotencyKey);
      onDispatch?.();
      posts.push(attempt.idempotencyKey);
      onDispatch?.();
      return secondResponse.promise;
    },
  });
  const pending = value.controller.acknowledgeArrival();
  while (posts.length < 2) await Promise.resolve();
  value.setContextGeneration(2);
  secondResponse.resolve(applied);
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' });
  value.publish(arrived(4));
  assert.equal(value.controller.isAcknowledgeArrivalActionable(), false);
  assert.deepEqual(posts, [keys[0], keys[0]]);
  assert.equal(value.creations(), 1);
});

test('controller result and state expose no attempt, key, transport, or trusted writer', async () => {
  const value = fixture();
  const state = value.controller.state() as Record<string, unknown>;
  const result = await value.controller.acknowledgeArrival() as Record<string, unknown>;
  assert.deepEqual(Object.keys(state), ['status']);
  assert.deepEqual(Object.keys(result), ['outcome']);
  assert.equal('attempt' in state, false);
  assert.equal('idempotencyKey' in state, false);
  assert.equal('attempt' in result, false);
  assert.equal('idempotencyKey' in result, false);
});
