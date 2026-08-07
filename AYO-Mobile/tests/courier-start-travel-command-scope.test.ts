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
const key = '77777777-7777-4777-8777-777777777777';

const handoff = (overrides: Partial<CourierHandoffSnapshot> = {}): CourierHandoffSnapshot => Object.freeze({
  status: 'pickup_current',
  pickupVersion: 4,
  updatedAt: '2026-08-07T06:00:00Z',
  presentationAction: 'start_travel',
  ...overrides,
});

function fixture() {
  let identity = { identityId: identityA, sessionId: sessionA, identityGeneration: 1 };
  let courier: { pickupId: string; contextGeneration: number; identityGeneration: number } | undefined = { pickupId: pickupA, contextGeneration: 1, identityGeneration: 1 };
  const scope = new CourierStartTravelCommandScope(
    () => identity,
    () => courier,
    (value) => createStartTravelAttempt(value, () => key),
  );
  return {
    scope,
    setIdentity: (next: typeof identity) => { identity = next; },
    setCourier: (next: typeof courier) => { courier = next; },
  };
}

test('fresh matching evidence creates one immutable attempt from trusted scope', () => {
  const { scope } = fixture();
  scope.publishFresh(pickupA, handoff());
  const attempt = scope.createForCurrentPickup();
  assert.deepEqual(attempt, {
    action: 'start_travel', pickupId: pickupA, expectedVersion: 4, idempotencyKey: key,
    identityId: identityA, sessionId: sessionA, identityGeneration: 1, contextGeneration: 1,
  });
  assert.equal(Object.isFrozen(attempt), true);
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
  assert.equal(scope.createForCurrentPickup()?.expectedVersion, 9);
});

test('identity and session replacement invalidate the old attempt', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const attempt = fixtureValue.scope.createForCurrentPickup();
  assert.ok(attempt);
  fixtureValue.setIdentity({ identityId: identityA, sessionId: sessionB, identityGeneration: 2 });
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), false);
  fixtureValue.setIdentity({ identityId: identityB, sessionId: sessionB, identityGeneration: 3 });
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), false);
});

test('courier invalidation and Pickup replacement invalidate the old attempt', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const attempt = fixtureValue.scope.createForCurrentPickup();
  assert.ok(attempt);
  fixtureValue.setCourier(undefined);
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), false);
  fixtureValue.setCourier({ pickupId: pickupB, contextGeneration: 2, identityGeneration: 1 });
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), false);
});

test('same courier refresh and presentation-only selection preserve command scope', () => {
  const { scope } = fixture();
  scope.publishFresh(pickupA, handoff());
  const attempt = scope.createForCurrentPickup();
  assert.ok(attempt);
  // Selection is deliberately absent from the trusted readers.
  scope.publishFresh(pickupA, handoff());
  assert.equal(scope.attemptIsCurrent(attempt), true);
});

test('creation and dispatch validation use the same canonical current-scope source', () => {
  const fixtureValue = fixture();
  fixtureValue.scope.publishFresh(pickupA, handoff());
  const attempt = fixtureValue.scope.createForCurrentPickup();
  assert.ok(attempt);
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), true);
  fixtureValue.scope.publishFresh(pickupA, handoff({ pickupVersion: 5 }));
  assert.equal(fixtureValue.scope.attemptIsCurrent(attempt), false);
});
