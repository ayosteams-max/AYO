import assert from 'node:assert/strict';
import test from 'node:test';

import type { CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';
import { createStartTravelAttempt } from '../domain/courier-start-travel-command.ts';
import { CourierStartTravelCommandScope } from '../services/courier-start-travel-command-scope.ts';

const identityA = '11111111-1111-4111-8111-111111111111';
const identityB = '22222222-2222-4222-8222-222222222222';
const sessionA = '33333333-3333-4333-8333-333333333333';
const sessionB = '44444444-4444-4444-8444-444444444444';
const pickupA = '55555555-5555-4555-8555-555555555555';
const pickupB = '66666666-6666-4666-8666-666666666666';
const keys = ['77777777-7777-4777-8777-777777777777', '88888888-8888-4888-8888-888888888888'] as const;

const handoff = (overrides: Partial<CourierHandoffSnapshot> = {}): CourierHandoffSnapshot => Object.freeze({
  status: 'pickup_current',
  pickupVersion: 4,
  updatedAt: '2026-08-07T06:00:00Z',
  presentationAction: 'start_travel',
  ...overrides,
});

function fixture() {
  let creations = 0;
  let identity = { identityId: identityA, sessionId: sessionA, identityGeneration: 1 };
  let courier: { pickupId: string; contextGeneration: number; identityGeneration: number } | undefined = { pickupId: pickupA, contextGeneration: 1, identityGeneration: 1 };
  const scope = new CourierStartTravelCommandScope(
    () => identity,
    () => courier && ({
      pickupId: courier.pickupId,
      contextGeneration: courier.contextGeneration,
      identityContinuity: Object.freeze({ isCurrent: () => identity.identityGeneration === courier?.identityGeneration }),
    }),
    (value) => createStartTravelAttempt(value, () => keys[creations++] ?? keys[1]),
  );
  return {
    scope,
    setIdentity: (next: typeof identity) => { identity = next; },
    setCourier: (next: typeof courier) => { courier = next; },
    creations: () => creations,
  };
}

test('presentation receives an opaque handle while trusted infrastructure retains the exact attempt', () => {
  const { scope, creations } = fixture();
  scope.publishFresh(pickupA, handoff());
  const handle = scope.createForCurrentPickup();
  assert.ok(handle);
  assert.deepEqual(Object.keys(handle), ['isCurrent']);
  for (const field of ['sessionId', 'identityGeneration', 'contextGeneration', 'idempotencyKey']) assert.equal(field in handle, false);
  const attempt = scope.resolveForTrustedUse(handle);
  assert.deepEqual(attempt, {
    action: 'start_travel', pickupId: pickupA, expectedVersion: 4, idempotencyKey: keys[0],
    identityId: identityA, sessionId: sessionA, identityGeneration: 1, contextGeneration: 1,
  });
  assert.equal(creations(), 1);
  assert.equal(handle.isCurrent(), true);
  assert.equal(scope.resolveForTrustedUse(handle), attempt);
  assert.equal(creations(), 1);
});

test('separate intents create separate opaque handles and internal keys', () => {
  const { scope, creations } = fixture();
  scope.publishFresh(pickupA, handoff());
  const first = scope.createForCurrentPickup(); const second = scope.createForCurrentPickup();
  assert.ok(first); assert.ok(second);
  assert.notEqual(scope.resolveForTrustedUse(first)?.idempotencyKey, scope.resolveForTrustedUse(second)?.idempotencyKey);
  assert.equal(creations(), 2);
});

test('stale, unavailable, non-presented, and mismatched evidence fail closed', () => {
  const { scope } = fixture();
  scope.publishFresh(pickupA, handoff());
  scope.clearFresh(pickupA);
  assert.equal(scope.createForCurrentPickup(), undefined);
  scope.publishFresh(pickupA, handoff({ presentationAction: 'none', status: 'travelling' }));
  assert.equal(scope.createForCurrentPickup(), undefined);
  scope.publishFresh(pickupB, handoff());
  assert.equal(scope.createForCurrentPickup(), undefined);
});

test('attempt version is taken only from the exact fresh handoff evidence', () => {
  const { scope } = fixture();
  scope.publishFresh(pickupA, handoff({ pickupVersion: 9 }));
  const handle = scope.createForCurrentPickup(); assert.ok(handle);
  assert.equal(scope.resolveForTrustedUse(handle)?.expectedVersion, 9);
});

test('identity and session replacement invalidate the old attempt', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const handle = fixtureValue.scope.createForCurrentPickup();
  assert.ok(handle);
  fixtureValue.setIdentity({ identityId: identityA, sessionId: sessionB, identityGeneration: 2 });
  assert.equal(handle.isCurrent(), false);
  fixtureValue.setIdentity({ identityId: identityB, sessionId: sessionB, identityGeneration: 3 });
  assert.equal(handle.isCurrent(), false);
});

test('courier invalidation and Pickup replacement invalidate the old attempt', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const handle = fixtureValue.scope.createForCurrentPickup();
  assert.ok(handle);
  fixtureValue.setCourier(undefined);
  assert.equal(handle.isCurrent(), false);
  fixtureValue.setCourier({ pickupId: pickupB, contextGeneration: 2, identityGeneration: 1 });
  assert.equal(handle.isCurrent(), false);
});

test('fresh evidence withdrawal invalidates the existing opaque handle without regenerating it', () => {
  const { scope, creations } = fixture();
  scope.publishFresh(pickupA, handoff());
  const handle = scope.createForCurrentPickup(); assert.ok(handle);
  scope.clearFresh(pickupA);
  assert.equal(handle.isCurrent(), false);
  assert.equal(creations(), 1);
});

test('same courier refresh and presentation-only selection preserve command scope', () => {
  const { scope } = fixture();
  scope.publishFresh(pickupA, handoff());
  const handle = scope.createForCurrentPickup();
  assert.ok(handle);
  // Selection is deliberately absent from the trusted readers.
  scope.publishFresh(pickupA, handoff());
  assert.equal(handle.isCurrent(), true);
});

test('creation and dispatch validation use the same canonical current-scope source', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const handle = fixtureValue.scope.createForCurrentPickup();
  assert.ok(handle);
  assert.equal(handle.isCurrent(), true);
  fixtureValue.scope.publishFresh(pickupA, handoff({ pickupVersion: 5 }));
  assert.equal(handle.isCurrent(), false);
});

test('retirement terminally invalidates handles, capabilities, resolution, and late evidence', () => {
  const { scope, creations } = fixture();
  scope.publishFresh(pickupA, handoff());
  const handle = scope.createForCurrentPickup(); assert.ok(handle);
  assert.equal(handle.isCurrent(), true);
  assert.ok(scope.currentScope());
  scope.retire();
  assert.equal(handle.isCurrent(), false);
  assert.equal(scope.currentScope(), undefined);
  assert.equal(scope.createForCurrentPickup(), undefined);
  assert.equal(scope.resolveForTrustedUse(handle), undefined);
  scope.publishFresh(pickupA, handoff());
  scope.clearFresh(pickupA);
  assert.equal(scope.currentScope(), undefined);
  assert.equal(scope.createForCurrentPickup(), undefined);
  assert.equal(creations(), 1);
});

test('forged and cross-scope handles cannot resolve internal attempts', () => {
  const first = fixture();
  const second = fixture();
  first.scope.publishFresh(pickupA, handoff());
  second.scope.publishFresh(pickupA, handoff());
  const handle = first.scope.createForCurrentPickup(); assert.ok(handle);
  const forged = Object.freeze({ isCurrent: () => true });
  assert.equal(first.scope.resolveForTrustedUse(forged), undefined);
  assert.equal(second.scope.resolveForTrustedUse(handle), undefined);
});

test('provider lifetime rehearsal preserves the live scope and real cleanup closes it', () => {
  const { scope, creations } = fixture();
  scope.publishFresh(pickupA, handoff());
  const handle = scope.createForCurrentPickup(); assert.ok(handle);
  scope.retainProviderLifetime();
  scope.releaseProviderLifetime();
  scope.retainProviderLifetime();
  scope.publishFresh(pickupA, handoff());
  assert.equal(handle.isCurrent(), true);
  assert.equal(creations(), 1);
  scope.releaseProviderLifetime();
  assert.equal(handle.isCurrent(), false);
  assert.equal(creations(), 1);
});

test('a replacement scope with identical values is independent from the retired owner', () => {
  const first = fixture();
  const second = fixture();
  first.scope.publishFresh(pickupA, handoff());
  const firstHandle = first.scope.createForCurrentPickup(); assert.ok(firstHandle);
  first.scope.retire();
  second.scope.publishFresh(pickupA, handoff());
  const secondHandle = second.scope.createForCurrentPickup(); assert.ok(secondHandle);
  assert.equal(firstHandle.isCurrent(), false);
  assert.equal(secondHandle.isCurrent(), true);
  assert.equal(second.scope.resolveForTrustedUse(firstHandle), undefined);
  assert.equal(first.creations(), 1);
  assert.equal(second.creations(), 1);
});
