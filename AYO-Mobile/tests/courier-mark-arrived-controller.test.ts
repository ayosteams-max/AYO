import assert from 'node:assert/strict';
import test from 'node:test';

import { createMarkArrivedAttempt, MarkArrivedAttemptInvalidError, MarkArrivedContractError, MarkArrivedOutcomeUnknownError, MarkArrivedRejectedError, type MarkArrivedAttempt } from '../domain/courier-mark-arrived-command.ts';
import type { CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';
import { CourierMarkArrivedCommandScope } from '../services/courier-mark-arrived-command-scope.ts';
import { CourierMarkArrivedCommandService } from '../services/courier-mark-arrived-command.ts';
import { CourierMarkArrivedController } from '../services/courier-mark-arrived-controller.ts';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const key = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const nextKey = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const travelling = (version = 5): CourierHandoffSnapshot => Object.freeze({ status: 'travelling', pickupVersion: version, updatedAt: '2026-08-08T01:00:00Z', presentationAction: 'mark_arrived' });
const arrived: CourierHandoffSnapshot = Object.freeze({ status: 'at_merchant', pickupVersion: 6, updatedAt: '2026-08-08T01:01:00Z', presentationAction: 'none' });
const waiting: CourierHandoffSnapshot = Object.freeze({ status: 'waiting_for_merchant', pickupVersion: 7, updatedAt: '2026-08-08T01:02:00Z', presentationAction: 'none' });

function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

function fixture() {
  let identity = { identityId, sessionId, identityGeneration: 1 };
  let continuity = true;
  let courier = { pickupId, contextGeneration: 1, identityContinuity: { isCurrent: () => continuity } };
  let creations = 0; let submissions = 0; let reconciliations = 0; let submitted: MarkArrivedAttempt | undefined;
  let submit: (attempt: MarkArrivedAttempt) => Promise<unknown> = async () => ({ pickupId, state: 'arrived_at_merchant', version: 6, travellingAt: '', arrivedAt: '', updatedAt: '' });
  let reconcile: () => Promise<any> = async () => ({ outcome: 'already_applied', pickup: {} });
  const scope = new CourierMarkArrivedCommandScope(() => identity, () => courier, (value) => {
    creations += 1; return createMarkArrivedAttempt(value, () => creations === 1 ? key : nextKey);
  });
  scope.publishFresh(pickupId, travelling());
  const controller = new CourierMarkArrivedController(scope, () => ({
    submit: async (attempt) => { submissions += 1; submitted = attempt; return submit(attempt) as never; },
    reconcile: async () => { reconciliations += 1; return reconcile(); },
  }));
  return { controller, scope, setIdentity: (next: typeof identity) => { identity = next; }, setCourier: (next: typeof courier) => { courier = next; }, revoke: () => { continuity = false; },
    onSubmit: (fn: typeof submit) => { submit = fn; }, onReconcile: (fn: typeof reconcile) => { reconcile = fn; }, creations: () => creations, submissions: () => submissions, reconciliations: () => reconciliations, submitted: () => submitted };
}

test('live mark-arrived evidence creates one immutable operation and repeated creation reuses it', () => {
  const value = fixture(); const first = value.controller.createAttempt(); const second = value.controller.createAttempt();
  assert.ok(first); assert.equal(second, first); assert.equal(value.creations(), 1);
  assert.equal(value.scope.resolveForSubmit(first)?.idempotencyKey, key);
  assert.equal(Object.isFrozen(value.scope.resolveForSubmit(first)), true);
});

test('ARRIVED and WAITING publication remove new-submit eligibility but preserve original reconciliation custody', async () => {
  for (const snapshot of [arrived, waiting]) {
    const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
    value.scope.publishFresh(pickupId, snapshot);
    assert.equal(value.scope.resolveForSubmit(handle), undefined);
    assert.ok(value.scope.resolveForOperation(handle));
    assert.equal(value.controller.createAttempt(), handle);
    assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'applied' });
    assert.equal(value.submissions(), 1); assert.equal(value.reconciliations(), 1); assert.equal(value.creations(), 1);
  }
});

test('newer corrected travelling evidence cannot mutate or retry the original operation', async () => {
  const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
  value.onReconcile(async () => ({ outcome: 'invalidated', reason: 'state_changed' }));
  const handle = value.controller.createAttempt(); assert.ok(handle); const original = value.scope.resolveForSubmit(handle); assert.ok(original);
  await value.controller.submit(handle); value.scope.publishFresh(pickupId, travelling(7));
  assert.equal(original.expectedVersion, 5); assert.equal(value.scope.resolveForSubmit(handle), undefined);
  assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'invalidated', reason: 'state_changed' });
  assert.equal(value.submissions(), 1); assert.equal(value.creations(), 1);
  const next = value.controller.createAttempt(); assert.ok(next); assert.notEqual(next, handle); assert.equal(value.scope.resolveForSubmit(next)?.expectedVersion, 7); assert.equal(value.creations(), 2);
});

test('newer corrected travelling evidence published during submit survives late outcome unknown', async () => {
  const gate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => gate.promise);
  value.onReconcile(async () => ({ outcome: 'invalidated', reason: 'state_changed' }));
  const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt);
  const pending = value.controller.submit(oldHandle); await Promise.resolve(); value.scope.publishFresh(pickupId, travelling(7));
  gate.resolve(Promise.reject(new MarkArrivedOutcomeUnknownError())); assert.deepEqual(await pending, { outcome: 'outcome_unknown' });
  assert.equal(value.scope.currentScope()?.pickupVersion, 7);
  assert.deepEqual(await value.controller.reconcile(oldHandle), { outcome: 'invalidated', reason: 'state_changed' });
  const nextHandle = value.controller.createAttempt(); assert.ok(nextHandle); const nextAttempt = value.scope.resolveForSubmit(nextHandle); assert.ok(nextAttempt);
  assert.notEqual(nextHandle, oldHandle); assert.equal(nextAttempt.expectedVersion, 7); assert.notEqual(nextAttempt.idempotencyKey, oldAttempt.idempotencyKey);
  assert.equal(value.submissions(), 1); assert.equal(value.creations(), 2);
});

test('newer ARRIVED and WAITING evidence survive every stale submit settlement class', async () => {
  const cases = [
    { snapshot: arrived, settle: () => undefined, expected: { outcome: 'applied' } },
    { snapshot: arrived, settle: () => Promise.reject(new MarkArrivedOutcomeUnknownError()), expected: { outcome: 'outcome_unknown' } },
    { snapshot: waiting, settle: () => Promise.reject(new MarkArrivedRejectedError('version_conflict')), expected: { outcome: 'rejected', reason: 'version_conflict' } },
    { snapshot: waiting, settle: () => Promise.reject(new MarkArrivedContractError()), expected: { outcome: 'rejected', reason: 'malformed_response' } },
  ] as const;
  for (const entry of cases) {
    const gate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => gate.promise);
    const handle = value.controller.createAttempt(); assert.ok(handle); const attempt = value.scope.resolveForSubmit(handle); assert.ok(attempt);
    const pending = value.controller.submit(handle); await Promise.resolve(); value.scope.publishFresh(pickupId, entry.snapshot); gate.resolve(entry.settle());
    assert.deepEqual(await pending, entry.expected);
    assert.equal(value.scope.publishRetryEvidence(attempt, { pickupId, state: 'travelling_to_merchant', version: 5, updatedAt: travelling().updatedAt, presentationAction: 'mark_arrived' }), false);
    assert.equal(value.submissions(), 1); assert.equal(value.creations(), 1);
  }
});

test('old rejection cannot erase newer actionable evidence', async () => {
  const gate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => gate.promise);
  const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt);
  const pending = value.controller.submit(oldHandle); await Promise.resolve(); value.scope.publishFresh(pickupId, travelling(7));
  gate.resolve(Promise.reject(new MarkArrivedRejectedError('transition_not_allowed')));
  assert.deepEqual(await pending, { outcome: 'rejected', reason: 'transition_not_allowed' });
  const nextHandle = value.controller.createAttempt(); assert.ok(nextHandle); const nextAttempt = value.scope.resolveForSubmit(nextHandle); assert.ok(nextAttempt);
  assert.equal(nextAttempt.expectedVersion, 7); assert.notEqual(nextAttempt.idempotencyKey, oldAttempt.idempotencyKey); assert.equal(value.submissions(), 1);
});

test('stale retry proof cannot overwrite newer evidence published during reconciliation', async () => {
  const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
  const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt); await value.controller.submit(oldHandle);
  const gate = deferred<any>(); value.onReconcile(async () => gate.promise); const pending = value.controller.reconcile(oldHandle); await Promise.resolve();
  value.scope.publishFresh(pickupId, travelling(7));
  gate.resolve({ outcome: 'retry_same_attempt', pickup: { pickupId, state: 'travelling_to_merchant', version: 5, updatedAt: travelling().updatedAt, presentationAction: 'mark_arrived' } });
  assert.deepEqual(await pending, { outcome: 'invalidated', reason: 'scope_changed' }); assert.equal(value.scope.currentScope()?.pickupVersion, 7);
  assert.deepEqual(await value.controller.submit(oldHandle), { outcome: 'invalidated', reason: 'scope_changed' }); assert.equal(value.submissions(), 1);
  const nextHandle = value.controller.createAttempt(); assert.ok(nextHandle); const nextAttempt = value.scope.resolveForSubmit(nextHandle); assert.ok(nextAttempt);
  assert.equal(nextAttempt.expectedVersion, 7); assert.notEqual(nextAttempt.idempotencyKey, oldAttempt.idempotencyKey); assert.equal(value.reconciliations(), 1);
});

test('submit is exact-live guarded while reconciliation uses operation continuity', async () => {
  const value = fixture(); const handle = value.controller.createAttempt(); assert.ok(handle);
  value.scope.publishFresh(pickupId, arrived);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(value.submissions(), 0);
});

test('concurrent submission and reconciliation are each single-flight and preserve one key', async () => {
  const submitGate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => submitGate.promise);
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const first = value.controller.submit(handle); const second = value.controller.submit(handle); assert.equal(first, second); await Promise.resolve(); assert.equal(value.submissions(), 1);
  submitGate.resolve(Promise.reject(new MarkArrivedOutcomeUnknownError()));
  assert.deepEqual(await first, { outcome: 'outcome_unknown' });
  const reconcileGate = deferred<any>(); value.onReconcile(async () => reconcileGate.promise);
  const check1 = value.controller.reconcile(handle); const check2 = value.controller.reconcile(handle); assert.equal(check1, check2); await Promise.resolve(); assert.equal(value.reconciliations(), 1);
  reconcileGate.resolve({ outcome: 'retry_same_attempt', pickup: { pickupId, state: 'travelling_to_merchant', version: 5, updatedAt: travelling().updatedAt, presentationAction: 'mark_arrived' } });
  assert.deepEqual(await check1, { outcome: 'retry_same_attempt' });
  value.onSubmit(async () => ({ pickupId, state: 'arrived_at_merchant', version: 6, travellingAt: '', arrivedAt: '', updatedAt: '' }));
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'applied' });
  assert.equal(value.submissions(), 2); assert.equal(value.submitted()?.idempotencyKey, key);
  assert.equal(value.scope.resolveForOperation(handle)?.idempotencyKey, key); assert.equal(value.creations(), 1);
});

test('same-handle submit callers share the exact flight across mid-flight authority loss', async () => {
  const gate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => gate.promise);
  const handle = value.controller.createAttempt(); assert.ok(handle); const attempt = value.scope.resolveForSubmit(handle); assert.ok(attempt);
  const first = value.controller.submit(handle); await Promise.resolve(); assert.equal(value.submissions(), 1);
  value.revoke(); const second = value.controller.submit(handle);
  assert.equal(second, first); assert.equal(value.submissions(), 1); assert.equal(value.creations(), 1);
  gate.resolve(Promise.reject(new MarkArrivedAttemptInvalidError()));
  const expected = { outcome: 'invalidated', reason: 'scope_changed' };
  assert.deepEqual(await first, expected); assert.deepEqual(await second, expected);
  assert.equal(value.submissions(), 1); assert.equal(value.creations(), 1); assert.equal(value.submitted()?.idempotencyKey, attempt.idempotencyKey);
});

test('same-handle reconcile callers share the exact flight across mid-flight authority loss', async () => {
  const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
  const handle = value.controller.createAttempt(); assert.ok(handle); const attempt = value.scope.resolveForSubmit(handle); assert.ok(attempt);
  await value.controller.submit(handle);
  const gate = deferred<any>(); value.onReconcile(async () => gate.promise);
  const first = value.controller.reconcile(handle); await Promise.resolve(); assert.equal(value.reconciliations(), 1);
  value.revoke(); const second = value.controller.reconcile(handle);
  assert.equal(second, first); assert.equal(value.reconciliations(), 1); assert.equal(value.creations(), 1);
  gate.resolve({ outcome: 'invalidated', reason: 'authority_lost' });
  const expected = { outcome: 'invalidated', reason: 'authority_lost' };
  assert.deepEqual(await first, expected); assert.deepEqual(await second, expected);
  assert.equal(value.reconciliations(), 1); assert.equal(value.creations(), 1); assert.equal(attempt.idempotencyKey, key);
});

test('different handle never joins the active controller-owned flight', async () => {
  const gate = deferred<unknown>(); const value = fixture(); value.onSubmit(async () => gate.promise);
  const handle = value.controller.createAttempt(); assert.ok(handle); const active = value.controller.submit(handle); await Promise.resolve();
  const unrelated = Object.freeze({ isCurrent: () => true });
  const rejected = value.controller.submit(unrelated);
  assert.notEqual(rejected, active); assert.deepEqual(await rejected, { outcome: 'invalidated', reason: 'non_current_operation' });
  assert.equal(value.submissions(), 1); assert.equal(value.creations(), 1);
  gate.resolve(Promise.reject(new MarkArrivedOutcomeUnknownError())); await active;
});

test('identity, session, generation, context, Pickup, continuity, release and retirement revoke operation custody', () => {
  const mutations = [
    (v: ReturnType<typeof fixture>) => v.setIdentity({ identityId: '44444444-4444-4444-8444-444444444444', sessionId, identityGeneration: 1 }),
    (v: ReturnType<typeof fixture>) => v.setIdentity({ identityId, sessionId: '44444444-4444-4444-8444-444444444444', identityGeneration: 1 }),
    (v: ReturnType<typeof fixture>) => v.setIdentity({ identityId, sessionId, identityGeneration: 2 }),
    (v: ReturnType<typeof fixture>) => v.setCourier({ pickupId, contextGeneration: 2, identityContinuity: { isCurrent: () => true } }),
    (v: ReturnType<typeof fixture>) => v.setCourier({ pickupId: '44444444-4444-4444-8444-444444444444', contextGeneration: 1, identityContinuity: { isCurrent: () => true } }),
    (v: ReturnType<typeof fixture>) => v.revoke(),
    (v: ReturnType<typeof fixture>) => v.scope.releaseProviderLifetime(),
    (v: ReturnType<typeof fixture>) => v.scope.retire(),
  ];
  for (const mutate of mutations) { const value = fixture(); const handle = value.controller.createAttempt(); assert.ok(handle); mutate(value); assert.equal(value.scope.resolveForOperation(handle), undefined); assert.equal(handle.isCurrent(), false); }
});

test('authority-revoked outcome-unknown operation cannot jam a later explicit identity intent', async () => {
  const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
  const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt);
  assert.deepEqual(await value.controller.submit(oldHandle), { outcome: 'outcome_unknown' });
  value.setIdentity({ identityId: '44444444-4444-4444-8444-444444444444', sessionId: '55555555-5555-4555-8555-555555555555', identityGeneration: 2 });
  value.setCourier({ pickupId, contextGeneration: 2, identityContinuity: { isCurrent: () => true } });
  assert.deepEqual(await value.controller.reconcile(oldHandle), { outcome: 'invalidated', reason: 'invalid_handle' });
  assert.equal(value.reconciliations(), 0); assert.equal(value.submissions(), 1);
  value.scope.publishFresh(pickupId, travelling());
  const newHandle = value.controller.createAttempt(); assert.ok(newHandle); assert.notEqual(newHandle, oldHandle);
  const newAttempt = value.scope.resolveForSubmit(newHandle); assert.ok(newAttempt); assert.equal(newAttempt.idempotencyKey, nextKey);
  assert.notEqual(newAttempt.idempotencyKey, oldAttempt.idempotencyKey); assert.equal(value.scope.resolveForOperation(oldHandle), undefined);
});

test('revoked Pickup operation cannot migrate and does not block a later explicit Pickup intent', async () => {
  const value = fixture(); const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt);
  const replacementPickupId = '44444444-4444-4444-8444-444444444444';
  value.setCourier({ pickupId: replacementPickupId, contextGeneration: 2, identityContinuity: { isCurrent: () => true } });
  assert.deepEqual(await value.controller.submit(oldHandle), { outcome: 'invalidated', reason: 'invalid_handle' }); assert.equal(value.submissions(), 0);
  value.scope.publishFresh(replacementPickupId, travelling());
  const newHandle = value.controller.createAttempt(); assert.ok(newHandle); const newAttempt = value.scope.resolveForSubmit(newHandle); assert.ok(newAttempt);
  assert.notEqual(newHandle, oldHandle); assert.equal(newAttempt.pickupId, replacementPickupId); assert.equal(newAttempt.idempotencyKey, nextKey);
  assert.notEqual(newAttempt.idempotencyKey, oldAttempt.idempotencyKey); assert.equal(value.scope.resolveForOperation(oldHandle), undefined);
});

test('revoked retry authorization cannot submit or block a later explicit intent', async () => {
  const value = fixture(); value.onSubmit(async () => { throw new MarkArrivedOutcomeUnknownError(); });
  value.onReconcile(async () => ({ outcome: 'retry_same_attempt', pickup: { pickupId, state: 'travelling_to_merchant', version: 5, updatedAt: travelling().updatedAt, presentationAction: 'mark_arrived' } }));
  const oldHandle = value.controller.createAttempt(); assert.ok(oldHandle); const oldAttempt = value.scope.resolveForSubmit(oldHandle); assert.ok(oldAttempt);
  await value.controller.submit(oldHandle); assert.deepEqual(await value.controller.reconcile(oldHandle), { outcome: 'retry_same_attempt' });
  value.setCourier({ pickupId, contextGeneration: 2, identityContinuity: { isCurrent: () => true } });
  assert.deepEqual(await value.controller.submit(oldHandle), { outcome: 'invalidated', reason: 'invalid_handle' }); assert.equal(value.submissions(), 1);
  value.scope.publishFresh(pickupId, travelling(8));
  const newHandle = value.controller.createAttempt(); assert.ok(newHandle); const newAttempt = value.scope.resolveForSubmit(newHandle); assert.ok(newAttempt);
  assert.notEqual(newHandle, oldHandle); assert.equal(newAttempt.expectedVersion, 8); assert.equal(newAttempt.idempotencyKey, nextKey);
  assert.notEqual(newAttempt.idempotencyKey, oldAttempt.idempotencyKey);
});

test('provider rehearsal can retain a released scope, but retired scope cannot revive', () => {
  const rehearsed = fixture(); const handle = rehearsed.controller.createAttempt(); assert.ok(handle);
  rehearsed.scope.releaseProviderLifetime(); assert.equal(handle.isCurrent(), false); rehearsed.scope.retainProviderLifetime(); assert.equal(handle.isCurrent(), true);
  rehearsed.scope.retire(); rehearsed.scope.retainProviderLifetime(); assert.equal(handle.isCurrent(), false);
});

test('late operation A cannot migrate to replacement owner B', async () => {
  const first = fixture(); const second = fixture();
  const handleA = first.controller.createAttempt(); assert.ok(handleA); first.scope.releaseProviderLifetime();
  assert.deepEqual(await first.controller.submit(handleA), { outcome: 'invalidated', reason: 'invalid_handle' });
  const handleB = second.controller.createAttempt(); assert.ok(handleB); assert.equal(second.scope.resolveForOperation(handleA), undefined); assert.equal(handleB.isCurrent(), true);
  assert.equal(first.submissions(), 0); assert.equal(second.submissions(), 0);
});

test('service reconciliation accepts lifecycle advancement only through operation continuity', async () => {
  const value = fixture(); const handle = value.controller.createAttempt(); assert.ok(handle); const attempt = value.scope.resolveForSubmit(handle); assert.ok(attempt);
  const response = { pickup_id: pickupId, state: 'waiting_for_pickup', version: 7, assigned_at: '2026-08-08T00:00:00Z', travelling_at: '2026-08-08T00:30:00Z', arrived_at: '2026-08-08T01:00:00Z', merchant_acknowledged_at: '2026-08-08T01:01:00Z', waiting_duration_seconds: 60, terminal_reason: null, updated_at: '2026-08-08T01:01:00Z', presentation_action: 'none' };
  const service = new CourierMarkArrivedCommandService({ post: async () => { throw new Error('no_post'); } }, async () => response, () => undefined, (candidate) => value.scope.operationIsCurrent(candidate));
  value.scope.publishFresh(pickupId, waiting);
  assert.deepEqual((await service.reconcile(attempt)).outcome, 'already_applied');
  value.revoke();
  assert.deepEqual(await service.reconcile(attempt), { outcome: 'invalidated', reason: 'authority_lost' });
});
