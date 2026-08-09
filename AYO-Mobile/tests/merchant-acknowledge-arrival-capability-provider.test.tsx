import { act, render } from '@testing-library/react-native';
import { StrictMode, useLayoutEffect } from 'react';

import {
  MerchantAcknowledgeArrivalInfrastructureProvider,
  useMerchantAcknowledgeArrivalCapability,
  type MerchantAcknowledgeArrivalPresentationCapability,
} from '@/contexts/merchant-acknowledge-arrival-capability';
import * as pickupContext from '@/contexts/merchant-operational-pickup';
import {
  MerchantAcknowledgeArrivalOutcomeUnknownError,
  type MerchantAcknowledgeArrivalAttempt,
  type MerchantAcknowledgeArrivalReconciliation,
  type MerchantAcknowledgeArrivalResult,
} from '@/domain/merchant-acknowledge-arrival-command';
import type { MerchantCourierPickupSnapshot } from '@/domain/merchant-courier-pickup-status';
import type { MerchantAcknowledgeArrivalCommandService } from '@/services/merchant-acknowledge-arrival-command';
import { PublicApiError } from '@/services/api-foundation';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const merchantId = '33333333-3333-4333-8333-333333333333';
const orderId = '44444444-4444-4444-8444-444444444444';
const pickupId = '55555555-5555-4555-8555-555555555555';

const pickup = (
  version = 4,
  action: 'acknowledge_arrival' | 'none' = 'acknowledge_arrival',
  currentPickupId = pickupId,
): MerchantCourierPickupSnapshot => Object.freeze({
  pickupId: currentPickupId,
  state: 'arrived_at_merchant',
  version,
  arrivedAt: '2026-08-09T00:00:00Z',
  updatedAt: '2026-08-09T00:00:00Z',
  presentationAction: action,
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
  const promise = new Promise<T>((settle) => { resolve = settle; });
  return { promise, resolve };
}

let capability!: MerchantAcknowledgeArrivalPresentationCapability;
function Observer() {
  const value = useMerchantAcknowledgeArrivalCapability();
  useLayoutEffect(() => { capability = value; }, [value]);
  return null;
}

type FakeService = Pick<MerchantAcknowledgeArrivalCommandService, 'submit' | 'reconcile'>;

function setup(service: FakeService) {
  let signal = 0;
  let operation: pickupContext.MerchantPickupOperationContextSnapshot | undefined;
  let continuityCurrent = true;
  const continuity = Object.freeze({ isCurrent: () => continuityCurrent });
  const read = {
    get state(): pickupContext.MerchantOperationalPickupState {
      return signal % 2 ? Object.freeze({ status: 'loading', orderId }) : Object.freeze({ status: 'idle' });
    },
    inspectOrder: async () => ({ status: 'idle' as const }),
    refresh: async () => ({ status: 'idle' as const }),
    clearInspection: () => { operation = undefined; },
  };
  const operationReader = Object.freeze({
    readMerchantPickupOperation: () => operation,
  });
  const readSpy = jest.spyOn(pickupContext, 'useMerchantOperationalPickup').mockImplementation(() => read);
  const operationSpy = jest.spyOn(pickupContext, 'useMerchantPickupOperationContext').mockImplementation(() => operationReader);
  const runtime = Object.freeze({
    readIdentity: () => Object.freeze({ identityId, sessionId, identityGeneration: 1 }),
    createMerchantAcknowledgeArrivalCommandService: jest.fn(async () => service as MerchantAcknowledgeArrivalCommandService),
  });
  const tree = (strict = false) => strict
    ? <StrictMode><MerchantAcknowledgeArrivalInfrastructureProvider identity={runtime}><Observer /></MerchantAcknowledgeArrivalInfrastructureProvider></StrictMode>
    : <MerchantAcknowledgeArrivalInfrastructureProvider identity={runtime}><Observer /></MerchantAcknowledgeArrivalInfrastructureProvider>;
  return {
    runtime,
    tree,
    publish(next: MerchantCourierPickupSnapshot, overrides: Partial<pickupContext.MerchantPickupOperationContextSnapshot> = {}) {
      signal += 1;
      operation = Object.freeze({ merchantId, orderId, pickupId: next.pickupId, pickup: next, contextGeneration: 1, identityContinuity: continuity, ...overrides });
    },
    retireContinuity() { continuityCurrent = false; },
    clear() { signal += 1; operation = undefined; },
    cleanup() { readSpy.mockRestore(); operationSpy.mockRestore(); },
  };
}

afterEach(() => jest.restoreAllMocks());

test('construction, Strict Mode rehearsal, and pure capability reads create no command or network work', async () => {
  const service = { submit: jest.fn(async () => applied), reconcile: jest.fn<Promise<MerchantAcknowledgeArrivalReconciliation>, [MerchantAcknowledgeArrivalAttempt]>() };
  const value = setup(service);
  const random = jest.spyOn(globalThis.crypto, 'randomUUID');
  const mounted = await render(value.tree(true));
  expect(Object.isFrozen(capability)).toBe(true);
  expect(Object.keys(capability).sort()).toEqual(['acknowledgeArrival', 'canAcknowledgeArrival', 'canReconcileAcknowledgeArrival', 'reconcileAcknowledgeArrival', 'state']);
  expect(capability.canAcknowledgeArrival()).toBe(false);
  expect(capability.canReconcileAcknowledgeArrival()).toBe(false);
  expect(random).not.toHaveBeenCalled();
  expect(value.runtime.createMerchantAcknowledgeArrivalCommandService).not.toHaveBeenCalled();
  expect(service.submit).not.toHaveBeenCalled();
  await mounted.unmount(); value.cleanup();
});

test('only the current trusted actionable operation publishes authority; public stale signal cannot manufacture it', async () => {
  const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup(4, 'none'));
  await mounted.rerender(value.tree());
  expect(capability.canAcknowledgeArrival()).toBe(false);
  value.publish(pickup());
  await mounted.rerender(value.tree());
  expect(capability.canAcknowledgeArrival()).toBe(true);
  value.clear();
  await mounted.rerender(value.tree());
  expect(capability.canAcknowledgeArrival()).toBe(false);
  await mounted.unmount(); value.cleanup();
});

test('one explicit ACK is single-flight, creates one attempt/key, and publishes reactive submitting/applied state', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalResult>();
  const attempts: MerchantAcknowledgeArrivalAttempt[] = [];
  const service = {
    submit: jest.fn(async (attempt: MerchantAcknowledgeArrivalAttempt) => { attempts.push(attempt); return gate.promise; }),
    reconcile: jest.fn(),
  } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  let first!: Promise<unknown>; let second!: Promise<unknown>;
  await act(async () => { first = capability.acknowledgeArrival(); second = capability.acknowledgeArrival(); await Promise.resolve(); });
  expect(first).toBe(second);
  expect(capability.state).toEqual({ status: 'submitting' });
  expect(service.submit).toHaveBeenCalledTimes(1);
  expect(attempts).toHaveLength(1);
  expect(attempts[0].idempotencyKey).toMatch(/^[0-9a-f-]{36}$/i);
  await act(async () => { gate.resolve(applied); await first; });
  expect(capability.state).toEqual({ status: 'applied' });
  expect(capability.canAcknowledgeArrival()).toBe(false);
  await mounted.unmount(); value.cleanup();
});

test('submitting and applied state from Order A are neutral for Order B', async () => {
  const gate = deferred<MerchantAcknowledgeArrivalResult>();
  const service = { submit: jest.fn(async () => gate.promise), reconcile: jest.fn() } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  let pending!: Promise<unknown>;
  await act(async () => { pending = capability.acknowledgeArrival(); await Promise.resolve(); });
  expect(capability.state).toEqual({ status: 'submitting' });

  value.publish(pickup(), { orderId: '77777777-7777-4777-8777-777777777777' });
  await mounted.rerender(value.tree());
  expect(capability.state).toEqual({ status: 'idle' });
  await act(async () => { gate.resolve(applied); await pending; });
  expect(capability.state).toEqual({ status: 'idle' });
  await mounted.unmount(); value.cleanup();
});

test.each([
  {
    status: 'applied',
    service: () => ({ submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService),
    settle: async () => { await capability.acknowledgeArrival(); },
  },
  {
    status: 'outcome_unknown',
    service: () => ({ submit: jest.fn(async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); }), reconcile: jest.fn() } as unknown as FakeService),
    settle: async () => { await capability.acknowledgeArrival(); },
  },
  {
    status: 'retry_same_attempt',
    service: () => ({
      submit: jest.fn(async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); }),
      reconcile: jest.fn(async () => Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: pickup() })),
    } as unknown as FakeService),
    settle: async () => { await capability.acknowledgeArrival(); await capability.reconcileAcknowledgeArrival(); },
  },
  {
    status: 'rejected',
    service: () => ({ submit: jest.fn(async () => { throw new PublicApiError('temporarily_unavailable', 409); }), reconcile: jest.fn() } as unknown as FakeService),
    settle: async () => { await capability.acknowledgeArrival(); },
  },
  {
    status: 'invalidated',
    service: () => ({ submit: jest.fn(async () => { throw new PublicApiError('access_denied', 403); }), reconcile: jest.fn() } as unknown as FakeService),
    settle: async () => { await capability.acknowledgeArrival(); },
  },
])('settled $status state from Order A is neutral for Order B', async ({ status, service, settle }) => {
  const value = setup(service());
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  await act(async () => { await settle(); });
  expect(capability.state.status).toBe(status);
  value.publish(pickup(), { orderId: '77777777-7777-4777-8777-777777777777' });
  await mounted.rerender(value.tree());
  expect(capability.state).toEqual({ status: 'idle' });
  await mounted.unmount(); value.cleanup();
});

test('temporary freshness loss is neutral and semantic restoration recovers retained uncertainty', async () => {
  const service = {
    submit: jest.fn(async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); }),
    reconcile: jest.fn(),
  } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  await act(async () => { await capability.acknowledgeArrival(); });
  expect(capability.state).toEqual({ status: 'outcome_unknown' });
  value.clear(); await mounted.rerender(value.tree());
  expect(capability.state).toEqual({ status: 'idle' });
  expect(capability.canReconcileAcknowledgeArrival()).toBe(false);
  value.publish(pickup()); await mounted.rerender(value.tree());
  expect(capability.state).toEqual({ status: 'outcome_unknown' });
  expect(capability.canReconcileAcknowledgeArrival()).toBe(true);
  await mounted.unmount(); value.cleanup();
});

test('an unexpected submit failure remains outcome_unknown for its publication and neutral after replacement', async () => {
  const service = {
    submit: jest.fn(async () => { throw new Error('unexpected'); }),
    reconcile: jest.fn(),
  } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  await act(async () => { await expect(capability.acknowledgeArrival()).rejects.toThrow('unexpected'); });
  expect(capability.state).toEqual({ status: 'outcome_unknown' });
  value.publish(pickup(), { orderId: '77777777-7777-4777-8777-777777777777' });
  await mounted.rerender(value.tree());
  expect(capability.state).toEqual({ status: 'idle' });
  await mounted.unmount(); value.cleanup();
});

test('outcome_unknown enables one explicit reconciliation and retry reuses the exact attempt and key', async () => {
  const attempts: MerchantAcknowledgeArrivalAttempt[] = [];
  let submits = 0;
  const service = {
    submit: jest.fn(async (attempt: MerchantAcknowledgeArrivalAttempt) => {
      attempts.push(attempt);
      if (++submits === 1) throw new MerchantAcknowledgeArrivalOutcomeUnknownError();
      return applied;
    }),
    reconcile: jest.fn(async () => Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: pickup() })),
  } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  let uncertain!: Awaited<ReturnType<MerchantAcknowledgeArrivalPresentationCapability['acknowledgeArrival']>>;
  await act(async () => { uncertain = await capability.acknowledgeArrival(); });
  expect(uncertain.outcome).toBe('outcome_unknown');
  expect(capability.canReconcileAcknowledgeArrival()).toBe(true);
  let first!: Promise<unknown>; let second!: Promise<unknown>;
  await act(async () => { first = capability.reconcileAcknowledgeArrival(); second = capability.reconcileAcknowledgeArrival(); await Promise.resolve(); });
  expect(first).toBe(second);
  await act(async () => { await first; });
  expect(service.reconcile).toHaveBeenCalledTimes(1);
  expect(capability.state).toEqual({ status: 'retry_same_attempt' });
  await act(async () => { await capability.acknowledgeArrival(); });
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toBe(attempts[0]);
  expect(attempts[1].idempotencyKey).toBe(attempts[0].idempotencyKey);
  await mounted.unmount(); value.cleanup();
});

test('consumed same-version evidence stays suppressed while genuinely newer ARRIVED becomes actionable', async () => {
  const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup(4)); await mounted.rerender(value.tree());
  await act(async () => { await capability.acknowledgeArrival(); });
  value.clear(); await mounted.rerender(value.tree());
  value.publish(pickup(4)); await mounted.rerender(value.tree());
  expect(capability.canAcknowledgeArrival()).toBe(false);
  value.publish(pickup(6)); await mounted.rerender(value.tree());
  expect(capability.canAcknowledgeArrival()).toBe(true);
  expect(service.submit).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

const stalePublicationCases: ReadonlyArray<Readonly<{
  dimension: string;
  nextPickup: MerchantCourierPickupSnapshot;
  overrides: Partial<pickupContext.MerchantPickupOperationContextSnapshot>;
  retireContinuity?: boolean;
}>> = [
  {
    dimension: 'merchantId',
    nextPickup: pickup(),
    overrides: { merchantId: '66666666-6666-4666-8666-666666666666' },
  },
  {
    dimension: 'orderId',
    nextPickup: pickup(),
    overrides: { orderId: '77777777-7777-4777-8777-777777777777' },
  },
  {
    dimension: 'pickupId',
    nextPickup: pickup(4, 'acknowledge_arrival', '88888888-8888-4888-8888-888888888888'),
    overrides: {},
  },
  {
    dimension: 'contextGeneration',
    nextPickup: pickup(),
    overrides: { contextGeneration: 2 },
  },
  {
    dimension: 'pickupVersion',
    nextPickup: pickup(5),
    overrides: {},
  },
  {
    dimension: 'identityContinuity',
    nextPickup: pickup(),
    overrides: { identityContinuity: Object.freeze({ isCurrent: () => true }) },
    retireContinuity: true,
  },
];

test.each(stalePublicationCases)(
  'applied presentation state is neutral when only $dimension changes',
  async ({ nextPickup, overrides, retireContinuity }) => {
    const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
    const value = setup(service);
    const mounted = await render(value.tree());
    value.publish(pickup()); await mounted.rerender(value.tree());
    await act(async () => { await capability.acknowledgeArrival(); });
    expect(capability.state).toEqual({ status: 'applied' });
    if (retireContinuity) value.retireContinuity();
    value.publish(nextPickup, overrides); await mounted.rerender(value.tree());
    expect(capability.state).toEqual({ status: 'idle' });
    await mounted.unmount(); value.cleanup();
  },
);

test.each(stalePublicationCases)(
  'an old capability fails closed when only $dimension changes',
  async ({ nextPickup, overrides, retireContinuity }) => {
    const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
    const value = setup(service);
    const random = jest.spyOn(globalThis.crypto, 'randomUUID');
    const mounted = await render(value.tree());
    value.publish(pickup()); await mounted.rerender(value.tree());
    const old = capability;

    if (retireContinuity) value.retireContinuity();
    value.publish(nextPickup, overrides);
    await mounted.rerender(value.tree());

    expect(old.canAcknowledgeArrival()).toBe(false);
    expect(old.canReconcileAcknowledgeArrival()).toBe(false);
    let result!: Awaited<ReturnType<MerchantAcknowledgeArrivalPresentationCapability['acknowledgeArrival']>>;
    await act(async () => { result = await old.acknowledgeArrival(); });
    expect(result).toEqual({ outcome: 'invalidated', reason: 'scope_changed' });
    expect(value.runtime.createMerchantAcknowledgeArrivalCommandService).not.toHaveBeenCalled();
    expect(random).not.toHaveBeenCalled();
    expect(service.submit).not.toHaveBeenCalled();
    expect(service.reconcile).not.toHaveBeenCalled();
    await mounted.unmount(); value.cleanup();
  },
);

test('an old reconcile capability fails closed after publication replacement without another GET', async () => {
  const service = {
    submit: jest.fn(async () => { throw new MerchantAcknowledgeArrivalOutcomeUnknownError(); }),
    reconcile: jest.fn(),
  } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  await act(async () => { await capability.acknowledgeArrival(); });
  const old = capability;
  expect(old.canReconcileAcknowledgeArrival()).toBe(true);

  value.publish(pickup(), { contextGeneration: 2 });
  await mounted.rerender(value.tree());

  expect(old.canAcknowledgeArrival()).toBe(false);
  expect(old.canReconcileAcknowledgeArrival()).toBe(false);
  let result!: Awaited<ReturnType<MerchantAcknowledgeArrivalPresentationCapability['reconcileAcknowledgeArrival']>>;
  await act(async () => { result = await old.reconcileAcknowledgeArrival(); });
  expect(result).toEqual({ outcome: 'invalidated', reason: 'scope_changed' });
  expect(service.reconcile).not.toHaveBeenCalled();
  await mounted.unmount(); value.cleanup();
});

test('a stale capability invocation cannot bind its invalidation to the replacement publication', async () => {
  const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  value.publish(pickup()); await mounted.rerender(value.tree());
  await act(async () => { await capability.acknowledgeArrival(); });
  const old = capability;
  value.publish(pickup(), { orderId: '77777777-7777-4777-8777-777777777777' });
  await mounted.rerender(value.tree());
  await act(async () => {
    await expect(old.acknowledgeArrival()).resolves.toEqual({ outcome: 'invalidated', reason: 'scope_changed' });
  });
  expect(capability.state).toEqual({ status: 'idle' });
  expect(service.submit).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('the bounded capability surface exposes no command custody internals', async () => {
  const service = { submit: jest.fn(async () => applied), reconcile: jest.fn() } as unknown as FakeService;
  const value = setup(service);
  const mounted = await render(value.tree());
  for (const hidden of ['controller', 'scope', 'attempt', 'handle', 'idempotencyKey', 'transport', 'service', 'dispatchObserver', 'writer']) {
    expect(capability).not.toHaveProperty(hidden);
  }
  await mounted.unmount(); value.cleanup();
});
