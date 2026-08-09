import { act, cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import { useLayoutEffect } from 'react';

import { MerchantOperationalOrders } from '@/components/merchant-operational-orders';
import * as identity from '@/contexts/identity-session';
import { LanguageProvider } from '@/contexts/language';
import * as pickupContext from '@/contexts/merchant-operational-pickup';
import { PublicApiError } from '@/services/api-foundation';

const merchantA = '11111111-1111-4111-8111-111111111111';
const merchantB = '22222222-2222-4222-8222-222222222222';
const orderA = '33333333-3333-4333-8333-333333333333';
const orderB = '44444444-4444-4444-8444-444444444444';

function view(merchantId: string, orderId: string, state = 'ready_for_pickup') {
  return { order: { order_id: orderId, merchant_id: merchantId, merchant_display_name: 'AYO Market', state,
    lines: [{ item_id: '55555555-5555-4555-8555-555555555555', item_version: 1, name: 'Ethiopian coffee', kind: 'product', category_id: null, quantity: 1, unit_price_minor: 1000, line_total_minor: 1000, currency: 'ETB', modifier_selections: [], customer_instructions: null }],
    pricing: { authority: 'commerce_pricing', policy_version: 'commerce.v1', subtotal_minor: 1000, currency: 'ETB', evidence_hash: 'a'.repeat(64) }, evidence_hash: 'b'.repeat(64), version: 2, created_at: '2026-08-09T01:00:00Z' }, timeline: [], rejection: null };
}

function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

type Harness = ReturnType<typeof setup>;
type ReadMock = jest.Mock<Promise<unknown>, [string, AbortSignal?]>;
function setup(read: ReadMock) {
  let continuityCurrent = true;
  let continuity = Object.freeze({ isCurrent: () => continuityCurrent });
  const pickup = {
    state: Object.freeze({ status: 'idle' as const }),
    inspectOrder: jest.fn<Promise<pickupContext.MerchantOperationalPickupState>, [string, AbortSignal?]>(async () => Object.freeze({ status: 'idle' as const })),
    refresh: jest.fn<Promise<pickupContext.MerchantOperationalPickupState>, [AbortSignal?]>(async () => Object.freeze({ status: 'idle' as const })),
    clearInspection: jest.fn(),
  };
  jest.spyOn(identity, 'useAuthenticatedRead').mockReturnValue(read);
  jest.spyOn(identity, 'useIdentityContinuity').mockImplementation(() => ({ readIdentityContinuity: () => continuity }));
  jest.spyOn(pickupContext, 'useMerchantOperationalPickup').mockReturnValue(pickup);
  return {
    pickup,
    replaceIdentity() { continuityCurrent = false; continuityCurrent = true; continuity = Object.freeze({ isCurrent: () => continuityCurrent }); },
    tree(merchantId = merchantA, name = 'Merchant A') { return <LanguageProvider><MerchantOperationalOrders merchantId={merchantId} merchantName={name} /></LanguageProvider>; },
  };
}

afterEach(async () => { await cleanup(); jest.restoreAllMocks(); });

test('merchant mount performs one bounded list GET, renders real orders, and performs no Pickup or POST work', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read);
  await render(value.tree());
  expect(read).toHaveBeenCalledTimes(1); expect(read.mock.calls[0][0]).toBe(`/mobile/merchants/${merchantA}/orders?limit=25`);
  expect(screen.getByText('Order 33333333')).toBeTruthy(); expect(value.pickup.inspectOrder).not.toHaveBeenCalled();
  expect(read.mock.calls.every(([path]) => !String(path).includes('courier-pickup'))).toBe(true);
});

test('empty and malformed lists fail safely without fake orders', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>().mockResolvedValueOnce([]).mockResolvedValueOnce([{ unsafe: true }]); const value = setup(read);
  const mounted = await render(value.tree()); await screen.findByText('No orders are available right now.');
  expect(screen.getByText('No orders are available right now.')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText('Refresh orders')); });
  expect(screen.getByText('AYO could not safely read these orders.')).toBeTruthy(); expect(value.pickup.inspectOrder).not.toHaveBeenCalled();
});

test('explicit server-returned order selection alone inspects the exact order once', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); await render(value.tree()); await screen.findByText('Order 33333333');
  const card = screen.getByLabelText('Order 33333333. Ready for pickup');
  await act(async () => { fireEvent.press(card); fireEvent.press(card); });
  expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1); expect(value.pickup.inspectOrder).toHaveBeenCalledWith(orderA);
  expect(screen.queryByText(/Acknowledge|Confirm courier|Courier is here/i)).toBeNull();
});

test('merchant replacement clears A selection, loads only B list, and never assigns a B order', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async (path: string) => path.includes(merchantA) ? [view(merchantA, orderA)] : [view(merchantB, orderB)]); const value = setup(read);
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  await mounted.rerender(value.tree(merchantB, 'Merchant B')); await screen.findByText('Order 44444444');
  expect(screen.queryByText('Order 33333333')).toBeNull(); expect(screen.getByText('Order 44444444')).toBeTruthy();
  expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1); expect(value.pickup.clearInspection).toHaveBeenCalled();
});

test('identity continuity replacement clears selection and reloads without automatic Pickup inspection', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); const mounted = await render(value.tree()); await screen.findByText('Order 33333333');
  await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); }); value.replaceIdentity();
  await mounted.rerender(value.tree()); await screen.findByText('Order 33333333');
  expect(read).toHaveBeenCalledTimes(2); expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1); expect(screen.queryByText('Selected order')).toBeNull();
});

test('selection A to B during pending Pickup keeps visible selection B and delegates race custody to PR #64', async () => {
  const pending = deferred<pickupContext.MerchantOperationalPickupState>();
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA), view(merchantA, orderB)]); const value = setup(read);
  value.pickup.inspectOrder.mockImplementationOnce(async () => pending.promise).mockResolvedValueOnce(Object.freeze({ status: 'idle' }));
  await render(value.tree()); await screen.findByText('Order 33333333');
  await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); fireEvent.press(screen.getByLabelText('Order 44444444. Ready for pickup')); });
  expect(screen.getAllByText('Order 44444444')).toHaveLength(2); expect(value.pickup.inspectOrder).toHaveBeenNthCalledWith(1, orderA); expect(value.pickup.inspectOrder).toHaveBeenNthCalledWith(2, orderB);
  await act(async () => { pending.resolve(Object.freeze({ status: 'unavailable', orderId: orderA })); await pending.promise; });
  expect(screen.getAllByText('Order 44444444')).toHaveLength(2);
});

test('explicit refresh is one list GET, retains weak-network display, and creates no row Pickup reads', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>().mockResolvedValueOnce([view(merchantA, orderA)]).mockRejectedValueOnce(new PublicApiError('temporarily_unavailable', 503)); const value = setup(read);
  await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Refresh orders')); });
  expect(read).toHaveBeenCalledTimes(2); expect(screen.getByText('Order 33333333')).toBeTruthy(); expect(screen.getByText('Showing earlier order information while the connection recovers.')).toBeTruthy(); expect(value.pickup.inspectOrder).not.toHaveBeenCalled();
});

test('authority loss clears selected order and trusted Pickup inspection', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>().mockResolvedValueOnce([view(merchantA, orderA)]).mockRejectedValueOnce(new PublicApiError('access_denied', 403)); const value = setup(read);
  await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); fireEvent.press(screen.getByLabelText('Refresh orders')); });
  expect(screen.getByText('This merchant area is no longer available.')).toBeTruthy(); expect(screen.queryByText('Order 33333333')).toBeNull(); expect(value.pickup.clearInspection).toHaveBeenCalled();
});
