import { act, render } from '@testing-library/react-native';
import { StrictMode, useLayoutEffect } from 'react';

import {
  MerchantOperationalPickupProvider,
  useMerchantOperationalPickup,
  useMerchantPickupOperationContext,
  type MerchantOperationalPickupRead,
  type MerchantPickupOperationContextReader,
} from '@/contexts/merchant-operational-pickup';
import * as identitySession from '@/contexts/identity-session';
import * as operationalContext from '@/contexts/operational-context';
import { MerchantCourierPickupContractError, type MerchantCourierPickupSnapshot } from '@/domain/merchant-courier-pickup-status';
import { PublicApiError } from '@/services/api-foundation';

const merchantA = '11111111-1111-4111-8111-111111111111';
const merchantB = '22222222-2222-4222-8222-222222222222';
const orderA = '33333333-3333-4333-8333-333333333333';
const orderB = '44444444-4444-4444-8444-444444444444';
const pickupA = '55555555-5555-4555-8555-555555555555';
const pickupB = '66666666-6666-4666-8666-666666666666';

const pickup = (pickupId: string, version = 4): MerchantCourierPickupSnapshot => Object.freeze({
  pickupId,
  state: 'arrived_at_merchant',
  version,
  arrivedAt: '2026-08-09T00:00:00Z',
  updatedAt: '2026-08-09T00:00:00Z',
  presentationAction: 'acknowledge_arrival',
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

let read!: MerchantOperationalPickupRead;
let trusted!: MerchantPickupOperationContextReader;

function Observer() {
  const nextRead = useMerchantOperationalPickup();
  const nextTrusted = useMerchantPickupOperationContext();
  useLayoutEffect(() => { read = nextRead; trusted = nextTrusted; }, [nextRead, nextTrusted]);
  return null;
}

function operational(selectedMerchant?: string): ReturnType<typeof operationalContext.useOperationalContext> {
  return {
    status: 'ready',
    areas: selectedMerchant ? [{
      key: `merchant:${selectedMerchant}` as const,
      kind: 'merchant', enterable: true, merchantId: selectedMerchant,
      displayName: 'Merchant', availability: 'available',
    }] : [],
    selected: selectedMerchant ? {
      key: `merchant:${selectedMerchant}` as const,
      kind: 'merchant', enterable: true, merchantId: selectedMerchant,
      displayName: 'Merchant', availability: 'available',
    } : undefined,
    chooserVisible: false,
    refreshing: false,
    refresh: async () => undefined,
    selectArea: () => undefined,
    showChooser: () => undefined,
    invalidateCourier: () => undefined,
  };
}

function setup(load: (merchantId: string, orderId: string, signal?: AbortSignal) => Promise<MerchantCourierPickupSnapshot>) {
  let selected: string | undefined = merchantA;
  let current = true;
  let continuity = Object.freeze({ isCurrent: () => current });
  const operationalSpy = jest.spyOn(operationalContext, 'useOperationalContext').mockImplementation(() => operational(selected));
  const identitySpy = jest.spyOn(identitySession, 'useIdentityContinuity').mockImplementation(() => ({ readIdentityContinuity: () => continuity }));
  const readSpy = jest.spyOn(identitySession, 'useAuthenticatedRead').mockImplementation(() => async () => { throw new Error('duplicate_authenticated_read'); });
  const service = { load: jest.fn(load) };
  const tree = (strict = false) => strict
    ? <StrictMode><MerchantOperationalPickupProvider service={service}><Observer /></MerchantOperationalPickupProvider></StrictMode>
    : <MerchantOperationalPickupProvider service={service}><Observer /></MerchantOperationalPickupProvider>;
  const cleanup = () => { operationalSpy.mockRestore(); identitySpy.mockRestore(); readSpy.mockRestore(); };
  return {
    service, tree, cleanup,
    setSelected: (value: string | undefined) => { selected = value; },
    replaceIdentity: () => { current = false; continuity = Object.freeze({ isCurrent: () => true }); },
  };
}

afterEach(() => { jest.restoreAllMocks(); });

test('construction and pure reads create no request and expose no trusted writer', async () => {
  const value = setup(async () => pickup(pickupA));
  const mounted = await render(value.tree());
  expect(value.service.load).not.toHaveBeenCalled();
  expect(read.state).toEqual({ status: 'idle' });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(Object.keys(read).sort()).toEqual(['inspectOrder', 'refresh', 'state']);
  expect(read).not.toHaveProperty('publishFresh');
  expect(read).not.toHaveProperty('contextGeneration');
  expect(read).not.toHaveProperty('pickupId');
  await mounted.unmount();
  value.cleanup();
});

test('canonical server Pickup response alone promotes the selected merchant/order operation', async () => {
  const value = setup(async (merchantId, orderId) => {
    expect(merchantId).toBe(merchantA);
    expect(orderId).toBe(orderA);
    return pickup(pickupA);
  });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state).toEqual({ status: 'ready', value: { merchantId: merchantA, orderId: orderA, pickup: pickup(pickupA) } });
  const operation = trusted.readMerchantPickupOperation();
  expect(operation).toMatchObject({ merchantId: merchantA, orderId: orderA, pickupId: pickupA, contextGeneration: 1 });
  expect(operation?.pickup).toEqual(pickup(pickupA));
  expect(value.service.load).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('refresh retires command freshness, is single-flight, and preserves same-operation generation', async () => {
  const refresh = deferred<MerchantCourierPickupSnapshot>();
  let calls = 0;
  const value = setup(async () => ++calls === 1 ? pickup(pickupA) : refresh.promise);
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  const firstGeneration = trusted.readMerchantPickupOperation()?.contextGeneration;
  let first!: Promise<unknown>; let second!: Promise<unknown>;
  await act(async () => { first = read.refresh(); second = read.refresh(); await Promise.resolve(); });
  expect(first).toBe(second);
  expect(read.state.status).toBe('refreshing');
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(2);
  await act(async () => { refresh.resolve(pickup(pickupA, 5)); await first; });
  expect(read.state.status).toBe('ready');
  expect(trusted.readMerchantPickupOperation()?.contextGeneration).toBe(firstGeneration);
  expect(trusted.readMerchantPickupOperation()?.pickup.version).toBe(5);
  await mounted.unmount(); value.cleanup();
});

test('order A late response cannot overwrite newer authoritative order B', async () => {
  const a = deferred<MerchantCourierPickupSnapshot>();
  const b = deferred<MerchantCourierPickupSnapshot>();
  const value = setup(async (_merchantId, orderId) => orderId === orderA ? a.promise : b.promise);
  const mounted = await render(value.tree());
  let pendingA!: Promise<unknown>; let pendingB!: Promise<unknown>;
  await act(async () => { pendingA = read.inspectOrder(orderA); pendingB = read.inspectOrder(orderB); await Promise.resolve(); });
  await act(async () => { b.resolve(pickup(pickupB)); await pendingB; });
  expect(trusted.readMerchantPickupOperation()).toMatchObject({ orderId: orderB, pickupId: pickupB, contextGeneration: 1 });
  await act(async () => { a.resolve(pickup(pickupA)); await pendingA; });
  expect(read.state).toEqual({ status: 'ready', value: { merchantId: merchantA, orderId: orderB, pickup: pickup(pickupB) } });
  expect(trusted.readMerchantPickupOperation()).toMatchObject({ orderId: orderB, pickupId: pickupB, contextGeneration: 1 });
  await mounted.unmount(); value.cleanup();
});

test('merchant and identity replacement retire pending or established authority', async () => {
  const pending = deferred<MerchantCourierPickupSnapshot>();
  const value = setup(async () => pending.promise);
  const mounted = await render(value.tree());
  let request!: Promise<unknown>;
  await act(async () => { request = read.inspectOrder(orderA); await Promise.resolve(); });
  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  await act(async () => { pending.resolve(pickup(pickupA)); await request; });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();

  value.replaceIdentity();
  await mounted.rerender(value.tree());
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  await mounted.unmount(); value.cleanup();
});

test('identity replacement while a read is pending ignores the old response', async () => {
  const pending = deferred<MerchantCourierPickupSnapshot>();
  const value = setup(async () => pending.promise);
  const mounted = await render(value.tree());
  let request!: Promise<unknown>;
  await act(async () => { request = read.inspectOrder(orderA); await Promise.resolve(); });
  value.replaceIdentity();
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  await act(async () => { pending.resolve(pickup(pickupA)); await request; });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  await mounted.unmount(); value.cleanup();
});

test.each([
  ['unavailable', new PublicApiError('not_found', 404)],
  ['malformed', new MerchantCourierPickupContractError()],
  ['authority_lost', new PublicApiError('access_denied', 403)],
] as const)('merchant switch retires %s terminal state and its order identity', async (status, failure) => {
  const value = setup(async () => { throw failure; });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state).toEqual({ status, orderId: orderA });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(1);

  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(read.state).not.toHaveProperty('orderId');
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('same selection preserves terminal state while continuity replacement retires it', async () => {
  const value = setup(async () => { throw new PublicApiError('not_found', 404); });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state).toEqual({ status: 'unavailable', orderId: orderA });

  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'unavailable', orderId: orderA });
  value.replaceIdentity();
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(read.state).not.toHaveProperty('orderId');
  expect(value.service.load).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('selection loss retires ready state without loading another operation', async () => {
  const value = setup(async () => pickup(pickupA));
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state.status).toBe('ready');
  expect(trusted.readMerchantPickupOperation()).toBeDefined();

  value.setSelected(undefined);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('direct merchant switch retires ready state and trusted operation without loading merchant B', async () => {
  const value = setup(async () => pickup(pickupA));
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(trusted.readMerchantPickupOperation()).toMatchObject({ merchantId: merchantA, orderId: orderA });
  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(1);
  await mounted.unmount(); value.cleanup();
});

test('merchant switch retires stale and refreshing presentation without an automatic read', async () => {
  const pendingRefreshResult = deferred<MerchantCourierPickupSnapshot>();
  let calls = 0;
  const value = setup(async () => {
    if (++calls === 1) return pickup(pickupA);
    if (calls === 2) throw new PublicApiError('temporarily_unavailable', 503);
    if (calls === 3) return pickup(pickupA);
    return pendingRefreshResult.promise;
  });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); await read.refresh(); });
  expect(read.state.status).toBe('stale');
  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(value.service.load).toHaveBeenCalledTimes(2);

  value.setSelected(merchantA);
  await mounted.rerender(value.tree());
  let pending!: Promise<unknown>;
  await act(async () => { pending = read.inspectOrder(orderA); await pending; });
  expect(read.state.status).toBe('ready');
  let pendingRefresh!: Promise<unknown>;
  await act(async () => { pendingRefresh = read.refresh(); await Promise.resolve(); });
  expect(read.state.status).toBe('refreshing');
  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(value.service.load).toHaveBeenCalledTimes(4);
  await act(async () => { pendingRefreshResult.resolve(pickup(pickupA)); await pendingRefresh; });
  expect(read.state).toEqual({ status: 'idle' });
  await mounted.unmount(); value.cleanup();
});

test('merchant switch removes invalid lookup input without an automatic read', async () => {
  const value = setup(async () => pickup(pickupA));
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder('../merchant-a-order'); });
  expect(read.state).toEqual({ status: 'unavailable', orderId: '../merchant-a-order' });
  value.setSelected(merchantB);
  await mounted.rerender(value.tree());
  expect(read.state).toEqual({ status: 'idle' });
  expect(read.state).not.toHaveProperty('orderId');
  expect(value.service.load).not.toHaveBeenCalled();
  await mounted.unmount(); value.cleanup();
});

test('transient refresh failure retains stale presentation but no fresh operation authority', async () => {
  let calls = 0;
  const value = setup(async () => {
    if (++calls === 1) return pickup(pickupA);
    throw new PublicApiError('temporarily_unavailable', 503);
  });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  await act(async () => { await read.refresh(); });
  expect(read.state).toEqual({ status: 'stale', value: { merchantId: merchantA, orderId: orderA, pickup: pickup(pickupA) } });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  await mounted.unmount(); value.cleanup();
});

test('caller cancellation retires freshness and cannot publish a late response', async () => {
  const pending = deferred<MerchantCourierPickupSnapshot>();
  const value = setup(async () => pending.promise);
  const mounted = await render(value.tree());
  const abort = new AbortController();
  let request!: Promise<unknown>;
  await act(async () => { request = read.inspectOrder(orderA, abort.signal); await Promise.resolve(); });
  abort.abort();
  await act(async () => { pending.resolve(pickup(pickupA)); await request; });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(read.state.status).toBe('unavailable');
  await mounted.unmount(); value.cleanup();
});

test('server Pickup replacement advances generation while malformed, absent, and auth failures publish no context', async () => {
  const outcomes: Array<MerchantCourierPickupSnapshot | Error> = [
    pickup(pickupA), pickup(pickupB), new PublicApiError('not_found', 404),
    new PublicApiError('access_denied', 403), new MerchantCourierPickupContractError(),
  ];
  const value = setup(async () => {
    const next = outcomes.shift()!;
    if (next instanceof Error) throw next;
    return next;
  });
  const mounted = await render(value.tree());
  await act(async () => { await read.inspectOrder(orderA); });
  expect(trusted.readMerchantPickupOperation()?.contextGeneration).toBe(1);
  await act(async () => { await read.refresh(); });
  expect(trusted.readMerchantPickupOperation()).toMatchObject({ pickupId: pickupB, contextGeneration: 2 });
  await act(async () => { await read.refresh(); });
  expect(read.state).toEqual({ status: 'unavailable', orderId: orderA });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state).toEqual({ status: 'authority_lost', orderId: orderA });
  await act(async () => { await read.inspectOrder(orderA); });
  expect(read.state).toEqual({ status: 'malformed', orderId: orderA });
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  await mounted.unmount(); value.cleanup();
});

test('invalid order lookup and Strict Mode rehearsal create no network or trusted Pickup identity', async () => {
  const value = setup(async () => pickup(pickupA));
  const mounted = await render(value.tree(true));
  await act(async () => { await read.inspectOrder('../order'); });
  expect(value.service.load).not.toHaveBeenCalled();
  expect(trusted.readMerchantPickupOperation()).toBeUndefined();
  expect(read.state.status).toBe('unavailable');
  await mounted.unmount(); value.cleanup();
});
