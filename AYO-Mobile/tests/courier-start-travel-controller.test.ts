import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createStartTravelAttempt,
  StartTravelAttemptInvalidError,
  StartTravelContractError,
  StartTravelOutcomeUnknownError,
  StartTravelRejectedError,
  type CourierCommandScope,
  type StartTravelAttempt,
} from '../domain/courier-start-travel-command.ts';
import type { CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { CourierStartTravelController } from '../services/courier-start-travel-controller.ts';
import type { CourierStartTravelCommandService } from '../services/courier-start-travel-command.ts';
import { CourierStartTravelCommandScope } from '../services/courier-start-travel-command-scope.ts';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const keys = ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'] as const;
const commandScope = (): CourierCommandScope => ({ identityId, sessionId, identityGeneration: 1, contextGeneration: 1, pickupId, pickupVersion: 4, presentationAction: 'start_travel' });
const handoff: CourierHandoffSnapshot = Object.freeze({ status: 'pickup_current', pickupVersion: 4, updatedAt: '2026-08-07T01:00:00Z', presentationAction: 'start_travel' });
const applied = Object.freeze({ pickupId, state: 'travelling_to_merchant' as const, version: 5, travellingAt: '2026-08-07T01:01:00Z', updatedAt: '2026-08-07T01:01:00Z' });

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function fixture(overrides: Partial<Pick<CourierStartTravelCommandService, 'submit' | 'reconcile'>> = {}) {
  let creations = 0;
  const scope = new CourierStartTravelCommandScope(
    () => ({ identityId, sessionId, identityGeneration: 1 }),
    () => ({ pickupId, contextGeneration: 1, identityContinuity: Object.freeze({ isCurrent: () => true }) }),
    (value) => createStartTravelAttempt(value, () => keys[creations++] ?? keys[1]),
  );
  scope.publishFresh(pickupId, handoff);
  let submissions = 0;
  let reconciliations = 0;
  let submittedAttempt: StartTravelAttempt | undefined;
  const service = {
    submit: async (attempt: StartTravelAttempt, signal?: AbortSignal) => {
      submissions += 1;
      submittedAttempt = attempt;
      if (overrides.submit) return overrides.submit(attempt, signal);
      return applied;
    },
    reconcile: async (attempt: StartTravelAttempt, signal?: AbortSignal) => {
      reconciliations += 1;
      if (overrides.reconcile) return overrides.reconcile(attempt, signal);
      return Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: Object.freeze({ pickupId, state: 'courier_assigned' as const, version: 4, updatedAt: handoff.updatedAt, presentationAction: 'start_travel' as const }) });
    },
  };
  const controller = new CourierStartTravelController(scope, () => service);
  return { controller, scope, creations: () => creations, submissions: () => submissions, reconciliations: () => reconciliations, submittedAttempt: () => submittedAttempt };
}

test('valid opaque handle resolves through its exact owner and submits the original internal attempt once', async () => {
  const value = fixture();
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const internal = value.scope.resolveForTrustedUse(handle); assert.ok(internal);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'applied' });
  assert.equal(value.submissions(), 1);
  assert.equal(value.submittedAttempt(), internal);
  assert.equal(value.submittedAttempt()?.idempotencyKey, keys[0]);
  assert.equal(value.creations(), 1);
  assert.equal(value.controller.createAttempt(), undefined);
});

test('forged, cross-scope, and released-owner handles fail closed without command invocation', async () => {
  const first = fixture(); const second = fixture();
  const handle = first.controller.createAttempt(); assert.ok(handle);
  const forged = Object.freeze({ isCurrent: () => true });
  assert.deepEqual(await first.controller.submit(forged), { outcome: 'invalidated', reason: 'invalid_handle' });
  assert.deepEqual(await second.controller.submit(handle), { outcome: 'invalidated', reason: 'invalid_handle' });
  first.scope.releaseProviderLifetime();
  assert.deepEqual(await first.controller.submit(handle), { outcome: 'invalidated', reason: 'invalid_handle' });
  assert.equal(first.submissions(), 0); assert.equal(second.submissions(), 0);
});

test('two concurrent submissions of one handle join the exact same single flight', async () => {
  const gate = deferred<typeof applied>();
  const value = fixture({ submit: async () => gate.promise });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const first = value.controller.submit(handle); const second = value.controller.submit(handle);
  assert.equal(first, second);
  await Promise.resolve();
  assert.equal(value.submissions(), 1);
  gate.resolve(applied);
  assert.deepEqual(await first, { outcome: 'applied' });
  assert.deepEqual(await second, { outcome: 'applied' });
});

test('scope-owned handles not installed by the controller cannot select an operation', async () => {
  const value = fixture();
  const first = value.scope.createForCurrentPickup(); const second = value.scope.createForCurrentPickup();
  assert.ok(first); assert.ok(second); assert.notEqual(first, second);
  const expected = { outcome: 'invalidated', reason: 'non_current_operation' } as const;
  assert.deepEqual(await value.controller.submit(first), expected);
  assert.deepEqual(await value.controller.submit(second), expected);
  assert.equal(value.submissions(), 0);
});

test('controller attempt creation reuses one unresolved handle and key', () => {
  const value = fixture();
  const first = value.controller.createAttempt(); const second = value.controller.createAttempt();
  assert.ok(first); assert.equal(second, first); assert.equal(value.creations(), 1);
  assert.equal(value.scope.resolveForTrustedUse(first)?.idempotencyKey, keys[0]);
});

test('outcome unknown preserves the same attempt, blocks a new key, and requires deliberate reconciliation', async () => {
  const value = fixture({
    submit: async () => { throw new StartTravelOutcomeUnknownError(); },
    reconcile: async () => Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: Object.freeze({ pickupId, state: 'courier_assigned' as const, version: 4, updatedAt: handoff.updatedAt, presentationAction: 'start_travel' as const }) }),
  });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  assert.equal(value.submissions(), 1);
  assert.equal(value.controller.createAttempt(), handle); assert.equal(value.creations(), 1);
  assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'retry_same_attempt' });
  assert.equal(value.reconciliations(), 1); assert.equal(value.submissions(), 1);
});

test('successful reconciliation withdraws stale start-travel evidence without fabricating a snapshot', async () => {
  const value = fixture({
    submit: async () => { throw new StartTravelOutcomeUnknownError(); },
    reconcile: async () => Object.freeze({ outcome: 'already_applied' as const, pickup: Object.freeze({ pickupId, state: 'travelling_to_merchant' as const, version: 5, updatedAt: applied.updatedAt, presentationAction: 'none' as const }) }),
  });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'applied' });
  assert.equal(handle.isCurrent(), false);
  assert.equal(value.controller.createAttempt(), undefined);
  assert.equal(value.creations(), 1);
});

test('version and transition rejection withdraw stale evidence and require fresh state', async () => {
  for (const reason of ['version_conflict', 'transition_not_allowed'] as const) {
    const value = fixture({ submit: async () => { throw new StartTravelRejectedError(reason); } });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    assert.deepEqual(await value.controller.submit(handle), { outcome: 'rejected', reason });
    assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'rejected', reason });
    assert.equal(value.reconciliations(), 0);
    assert.equal(handle.isCurrent(), false);
    assert.equal(value.controller.createAttempt(), undefined);
  }
});

test('scope invalidation before dispatch is bounded and cannot generate a replacement intent', async () => {
  const value = fixture({ submit: async () => { throw new StartTravelAttemptInvalidError(); } });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const expected = { outcome: 'invalidated', reason: 'scope_changed' } as const;
  assert.deepEqual(await value.controller.submit(handle), expected);
  assert.deepEqual(await value.controller.reconcile(handle), expected);
  assert.equal(value.reconciliations(), 0);
  assert.equal(value.controller.createAttempt(), undefined);
  assert.equal(value.creations(), 1);
});

test('controller A late result cannot create state or retry capability in controller B', async () => {
  const gate = deferred<typeof applied>();
  const first = fixture({ submit: async () => gate.promise }); const second = fixture();
  const handleA = first.controller.createAttempt(); assert.ok(handleA);
  const pendingA = first.controller.submit(handleA);
  first.scope.releaseProviderLifetime();
  const handleB = second.controller.createAttempt(); assert.ok(handleB);
  gate.resolve(applied);
  assert.deepEqual(await pendingA, { outcome: 'applied' });
  assert.equal(handleA.isCurrent(), false);
  assert.equal(handleB.isCurrent(), true);
  assert.equal(second.submissions(), 0);
  assert.deepEqual(await second.controller.submit(handleA), { outcome: 'invalidated', reason: 'invalid_handle' });
});

test('abort is passed to the existing service and controller adds no retry', async () => {
  const abort = new AbortController(); abort.abort();
  let received: AbortSignal | undefined;
  const value = fixture({ submit: async (_attempt, signal) => { received = signal; throw new StartTravelAttemptInvalidError(); } });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  assert.deepEqual(await value.controller.submit(handle, abort.signal), { outcome: 'invalidated', reason: 'scope_changed' });
  assert.equal(received, abort.signal); assert.equal(value.submissions(), 1);
});

test('403 and 404 authority loss settle, withdraw evidence, and cannot freely resubmit', async () => {
  for (const status of [403, 404]) {
    const value = fixture({ submit: async () => { throw new PublicApiError(status === 403 ? 'access_denied' : 'not_found', status); } });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    const expected = { outcome: 'invalidated', reason: 'authority_lost' } as const;
    assert.deepEqual(await value.controller.submit(handle), expected);
    assert.deepEqual(await value.controller.submit(handle), expected);
    assert.deepEqual(await value.controller.reconcile(handle), expected);
    assert.equal(value.reconciliations(), 0);
    assert.equal(value.submissions(), 1);
    assert.equal(handle.isCurrent(), false);
    assert.equal(value.controller.createAttempt(), undefined);
    assert.equal(value.creations(), 1);
  }
});

test('post-refresh 401 settles as authority loss and cannot freely resubmit', async () => {
  const value = fixture({ submit: async () => { throw new PublicApiError('session_expired', 401); } });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const expected = { outcome: 'invalidated', reason: 'authority_lost' } as const;
  assert.deepEqual(await value.controller.submit(handle), expected);
  assert.deepEqual(await value.controller.submit(handle), expected);
  assert.deepEqual(await value.controller.reconcile(handle), expected);
  assert.equal(value.reconciliations(), 0);
  assert.equal(value.submissions(), 1);
  assert.equal(value.creations(), 1);
});

test('unknown 409 is definitive refresh-required rejection, not outcome unknown', async () => {
  const value = fixture({ submit: async () => { throw new PublicApiError('temporarily_unavailable', 409); } });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const expected = { outcome: 'rejected', reason: 'refresh_required' } as const;
  assert.deepEqual(await value.controller.submit(handle), expected);
  assert.deepEqual(await value.controller.submit(handle), expected);
  assert.deepEqual(await value.controller.reconcile(handle), expected);
  assert.equal(value.reconciliations(), 0);
  assert.equal(value.submissions(), 1);
  assert.equal(handle.isCurrent(), false);
  assert.equal(value.creations(), 1);
});

test('other definitive 4xx and malformed responses are bounded while unexpected bugs remain visible', async () => {
  const definitive = fixture({ submit: async () => { throw new PublicApiError('feature_unavailable', 422); } });
  const definitiveHandle = definitive.controller.createAttempt(); assert.ok(definitiveHandle);
  assert.deepEqual(await definitive.controller.submit(definitiveHandle), { outcome: 'rejected', reason: 'refresh_required' });
  assert.equal(definitive.submissions(), 1);

  const malformed = fixture({ submit: async () => { throw new PublicApiError('malformed_response', 200); } });
  const malformedHandle = malformed.controller.createAttempt(); assert.ok(malformedHandle);
  assert.deepEqual(await malformed.controller.submit(malformedHandle), { outcome: 'rejected', reason: 'malformed_response' });

  const bug = fixture({ submit: async () => { throw new Error('programmer_fault'); } });
  const bugHandle = bug.controller.createAttempt(); assert.ok(bugHandle);
  await assert.rejects(bug.controller.submit(bugHandle), /programmer_fault/);
  assert.equal(bug.submissions(), 1);
});

test('applied is monotonic and never-submitted reconciliation fails closed without a GET', async () => {
  const appliedValue = fixture();
  const appliedHandle = appliedValue.controller.createAttempt(); assert.ok(appliedHandle);
  assert.deepEqual(await appliedValue.controller.submit(appliedHandle), { outcome: 'applied' });
  assert.deepEqual(await appliedValue.controller.reconcile(appliedHandle), { outcome: 'applied' });
  assert.deepEqual(await appliedValue.controller.reconcile(appliedHandle), { outcome: 'applied' });
  assert.equal(appliedValue.reconciliations(), 0);

  const neverSubmitted = fixture();
  const unusedHandle = neverSubmitted.controller.createAttempt(); assert.ok(unusedHandle);
  assert.deepEqual(await neverSubmitted.controller.reconcile(unusedHandle), { outcome: 'rejected', reason: 'reconciliation_not_available' });
  assert.equal(neverSubmitted.reconciliations(), 0);
  assert.equal(neverSubmitted.creations(), 1);
});

test('ambiguous reconciliation terminal results remain monotonic', async () => {
  for (const reason of ['authority_lost', 'state_changed'] as const) {
    const value = fixture({
      submit: async () => { throw new StartTravelOutcomeUnknownError(); },
      reconcile: async () => Object.freeze({ outcome: 'invalidated' as const, reason }),
    });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
    const expected = { outcome: 'invalidated', reason } as const;
    assert.deepEqual(await value.controller.reconcile(handle), expected);
    assert.deepEqual(await value.controller.reconcile(handle), expected);
    assert.equal(value.reconciliations(), 1);
    assert.equal(value.creations(), 1);
  }
});

test('retry-same-attempt reconciliation runs once and preserves the exact attempt and key', async () => {
  const value = fixture({ submit: async () => { throw new StartTravelOutcomeUnknownError(); } });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  const attempt = value.scope.resolveForTrustedUse(handle); assert.ok(attempt);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'retry_same_attempt' });
  assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'retry_same_attempt' });
  assert.equal(value.reconciliations(), 1);
  assert.equal(value.scope.resolveForTrustedUse(handle), attempt);
  assert.equal(attempt.idempotencyKey, keys[0]);
  assert.equal(value.creations(), 1);
});

test('submit and reconcile share one in-flight operation in either direction', async () => {
  const submitGate = deferred<typeof applied>();
  const submitting = fixture({ submit: async () => submitGate.promise });
  const submitHandle = submitting.controller.createAttempt(); assert.ok(submitHandle);
  const submitFlight = submitting.controller.submit(submitHandle);
  assert.equal(submitting.controller.reconcile(submitHandle), submitFlight);
  assert.equal(submitting.reconciliations(), 0);
  submitGate.resolve(applied);
  assert.deepEqual(await submitFlight, { outcome: 'applied' });

  const reconcileGate = deferred<Readonly<{ outcome: 'retry_same_attempt'; pickup: Readonly<{ pickupId: string; state: 'courier_assigned'; version: number; updatedAt: string; presentationAction: 'start_travel' }> }>>();
  const reconciling = fixture({
    submit: async () => { throw new StartTravelOutcomeUnknownError(); },
    reconcile: async () => reconcileGate.promise,
  });
  const reconcileHandle = reconciling.controller.createAttempt(); assert.ok(reconcileHandle);
  assert.deepEqual(await reconciling.controller.submit(reconcileHandle), { outcome: 'outcome_unknown' });
  const reconcileFlight = reconciling.controller.reconcile(reconcileHandle);
  assert.equal(reconciling.controller.submit(reconcileHandle), reconcileFlight);
  await Promise.resolve();
  assert.equal(reconciling.reconciliations(), 1);
  assert.equal(reconciling.submissions(), 1);
  reconcileGate.resolve(Object.freeze({ outcome: 'retry_same_attempt', pickup: Object.freeze({ pickupId, state: 'courier_assigned', version: 4, updatedAt: handoff.updatedAt, presentationAction: 'start_travel' }) }));
  assert.deepEqual(await reconcileFlight, { outcome: 'retry_same_attempt' });
});

test('an old different-version handle cannot evict an in-flight newer operation', async () => {
  const gate = deferred<typeof applied>();
  let calls = 0;
  const value = fixture({ submit: async () => ++calls === 1 ? applied : gate.promise });
  const handleA = value.controller.createAttempt(); assert.ok(handleA);
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'applied' });
  value.scope.publishFresh(pickupId, Object.freeze({ ...handoff, pickupVersion: 5 }));
  const handleB = value.controller.createAttempt(); assert.ok(handleB); assert.notEqual(handleB, handleA);
  const pendingB = value.controller.submit(handleB);
  const staleA = value.controller.submit(handleA);
  await Promise.resolve();
  assert.deepEqual(await staleA, { outcome: 'invalidated', reason: 'non_current_operation' });
  assert.equal(value.submissions(), 2);
  gate.resolve(applied);
  assert.deepEqual(await pendingB, { outcome: 'applied' });
  assert.deepEqual(await value.controller.submit(handleB), { outcome: 'applied' });
  assert.equal(value.submissions(), 2);
});

test('old handle cannot displace newer ambiguity or its exact-key reconciliation custody', async () => {
  let calls = 0;
  const value = fixture({
    submit: async () => { if (++calls === 1) return applied; throw new StartTravelOutcomeUnknownError(); },
    reconcile: async (attempt) => {
      assert.equal(attempt.idempotencyKey, keys[1]);
      return Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: Object.freeze({ pickupId, state: 'courier_assigned' as const, version: 5, updatedAt: handoff.updatedAt, presentationAction: 'start_travel' as const }) });
    },
  });
  const handleA = value.controller.createAttempt(); assert.ok(handleA);
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'applied' });
  value.scope.publishFresh(pickupId, Object.freeze({ ...handoff, pickupVersion: 5 }));
  const handleB = value.controller.createAttempt(); assert.ok(handleB);
  const attemptB = value.scope.resolveForTrustedUse(handleB); assert.ok(attemptB);
  assert.equal(attemptB.idempotencyKey, keys[1]);
  assert.deepEqual(await value.controller.submit(handleB), { outcome: 'outcome_unknown' });
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'invalidated', reason: 'non_current_operation' });
  assert.equal(value.submissions(), 2);
  assert.deepEqual(await value.controller.reconcile(handleB), { outcome: 'retry_same_attempt' });
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'invalidated', reason: 'non_current_operation' });
  assert.deepEqual(await value.controller.reconcile(handleB), { outcome: 'retry_same_attempt' });
  assert.equal(value.reconciliations(), 1);
  assert.equal(value.scope.resolveForTrustedUse(handleB), attemptB);
  assert.equal(value.creations(), 2);
});

test('only explicit createAttempt may replace terminal operation ownership', async () => {
  const value = fixture();
  const handleA = value.controller.createAttempt(); assert.ok(handleA);
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'applied' });
  value.scope.publishFresh(pickupId, Object.freeze({ ...handoff, pickupVersion: 5 }));
  const handleB = value.controller.createAttempt(); assert.ok(handleB); assert.notEqual(handleB, handleA);
  assert.deepEqual(await value.controller.submit(handleA), { outcome: 'invalidated', reason: 'non_current_operation' });
  assert.equal(value.submissions(), 1);
  assert.deepEqual(await value.controller.submit(handleB), { outcome: 'applied' });
  assert.equal(value.submissions(), 2);
  assert.equal(value.creations(), 2);
});

test('definitive reconciliation errors settle once and withdraw stale evidence', async () => {
  const cases = [
    [new PublicApiError('session_expired', 401), { outcome: 'invalidated', reason: 'authority_lost' }],
    [new StartTravelContractError(), { outcome: 'rejected', reason: 'malformed_response' }],
    [new PublicApiError('malformed_response', 200), { outcome: 'rejected', reason: 'malformed_response' }],
    [new PublicApiError('temporarily_unavailable', 409), { outcome: 'rejected', reason: 'refresh_required' }],
    [new StartTravelAttemptInvalidError(), { outcome: 'invalidated', reason: 'scope_changed' }],
  ] as const;
  for (const [error, expected] of cases) {
    const value = fixture({
      submit: async () => { throw new StartTravelOutcomeUnknownError(); },
      reconcile: async () => { throw error; },
    });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
    assert.deepEqual(await value.controller.reconcile(handle), expected);
    assert.equal(handle.isCurrent(), false);
    assert.deepEqual(await value.controller.reconcile(handle), expected);
    assert.equal(value.reconciliations(), 1);
    assert.equal(value.creations(), 1);
  }
});

test('transient reconciliation failures preserve ambiguity and permit a later deliberate GET', async () => {
  for (const transient of [
    new PublicApiError('temporarily_unavailable'),
    new PublicApiError('request_cancelled'),
    new PublicApiError('temporarily_unavailable', 503),
  ]) {
    let calls = 0;
    const value = fixture({
      submit: async () => { throw new StartTravelOutcomeUnknownError(); },
      reconcile: async () => {
        if (++calls === 1) throw transient;
        return Object.freeze({ outcome: 'already_applied' as const, pickup: Object.freeze({ pickupId, state: 'travelling_to_merchant' as const, version: 5, updatedAt: applied.updatedAt, presentationAction: 'none' as const }) });
      },
    });
    const handle = value.controller.createAttempt(); assert.ok(handle);
    const attempt = value.scope.resolveForTrustedUse(handle); assert.ok(attempt);
    assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
    assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'outcome_unknown' });
    assert.equal(handle.isCurrent(), true);
    assert.equal(value.reconciliations(), 1);
    assert.equal(value.scope.resolveForTrustedUse(handle), attempt);
    assert.equal(value.creations(), 1);
    assert.deepEqual(await value.controller.reconcile(handle), { outcome: 'applied' });
    assert.equal(value.reconciliations(), 2);
    assert.equal(value.submissions(), 1);
    assert.equal(value.creations(), 1);
  }
});

test('unexpected reconciliation bugs remain visible without fabricating domain truth', async () => {
  const value = fixture({
    submit: async () => { throw new StartTravelOutcomeUnknownError(); },
    reconcile: async () => { throw new Error('reconciliation_programmer_fault'); },
  });
  const handle = value.controller.createAttempt(); assert.ok(handle);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  await assert.rejects(value.controller.reconcile(handle), /reconciliation_programmer_fault/);
  assert.equal(value.reconciliations(), 1);
  assert.deepEqual(await value.controller.submit(handle), { outcome: 'outcome_unknown' });
  assert.equal(value.submissions(), 1);
  assert.equal(value.creations(), 1);
});
