import { act, cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import { StrictMode, type ReactElement } from 'react';

import { MerchantOperationalOrders } from '@/components/merchant-operational-orders';
import * as identity from '@/contexts/identity-session';
import { LanguageProvider } from '@/contexts/language';
import * as acknowledgeContext from '@/contexts/merchant-acknowledge-arrival-capability';
import * as pickupContext from '@/contexts/merchant-operational-pickup';
import { merchantOperationalOrderCopy } from '@/localization/merchant-operational-orders';
import { PublicApiError } from '@/services/api-foundation';
import type { MerchantAcknowledgeArrivalControllerState } from '@/services/merchant-acknowledge-arrival-controller';

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
  let retireContinuity = () => undefined;
  const createContinuity = () => {
    let current = true;
    retireContinuity = () => { current = false; };
    return Object.freeze({ isCurrent: () => current });
  };
  let continuity = createContinuity();
  const pickup = {
    state: Object.freeze({ status: 'idle' as const }),
    inspectOrder: jest.fn<Promise<pickupContext.MerchantOperationalPickupState>, [string, AbortSignal?]>(async () => Object.freeze({ status: 'idle' as const })),
    refresh: jest.fn<Promise<pickupContext.MerchantOperationalPickupState>, [AbortSignal?]>(async () => Object.freeze({ status: 'idle' as const })),
    clearInspection: jest.fn(),
  };
  let acknowledgementState: MerchantAcknowledgeArrivalControllerState = Object.freeze({ status: 'idle' });
  let acknowledgementAvailable = false;
  let reconciliationAvailable = false;
  const acknowledgeArrival = jest.fn(async () => Object.freeze({ outcome: 'applied' as const }));
  const reconcileAcknowledgeArrival = jest.fn(async () => Object.freeze({ outcome: 'applied' as const }));
  jest.spyOn(identity, 'useAuthenticatedRead').mockReturnValue(read);
  jest.spyOn(identity, 'useIdentityContinuity').mockImplementation(() => ({ readIdentityContinuity: () => continuity }));
  jest.spyOn(pickupContext, 'useMerchantOperationalPickup').mockReturnValue(pickup);
  jest.spyOn(acknowledgeContext, 'useMerchantAcknowledgeArrivalCapability').mockImplementation(() => Object.freeze({
    state: acknowledgementState,
    canAcknowledgeArrival: () => acknowledgementAvailable,
    canReconcileAcknowledgeArrival: () => reconciliationAvailable,
    acknowledgeArrival,
    reconcileAcknowledgeArrival,
  }));
  return {
    pickup,
    acknowledgeArrival,
    reconcileAcknowledgeArrival,
    setAcknowledgement(next: MerchantAcknowledgeArrivalControllerState, canAcknowledge = false, canReconcile = false) {
      acknowledgementState = next; acknowledgementAvailable = canAcknowledge; reconciliationAvailable = canReconcile;
    },
    currentContinuity: () => continuity,
    replaceIdentity() {
      const previous = continuity;
      retireContinuity();
      continuity = createContinuity();
      return { previous, replacement: continuity };
    },
    tree(merchantId = merchantA, name = 'Merchant A', strict = false) {
      const content = <LanguageProvider><MerchantOperationalOrders merchantId={merchantId} merchantName={name} /></LanguageProvider>;
      return strict ? <StrictMode>{content}</StrictMode> : content;
    },
  };
}

type SynchronousRenderer = Readonly<{
  root: Readonly<{ findByProps(props: Readonly<Record<string, unknown>>): Readonly<{ props: Readonly<{ onPress(): void }> }> }>;
  toJSON(): unknown;
  update(element: ReactElement): void;
  unmount(): void;
  unstable_flushSync(callback: () => void): void;
}>;

const testRenderer = jest.requireActual('react-test-renderer') as Readonly<{
  create(element: ReactElement): SynchronousRenderer;
}>;

function renderedText(renderer: SynchronousRenderer) {
  return JSON.stringify(renderer.toJSON());
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
  await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); }); const replacement = value.replaceIdentity();
  expect(replacement.previous.isCurrent()).toBe(false); expect(replacement.replacement.isCurrent()).toBe(true);
  await mounted.rerender(value.tree()); await screen.findByText('Order 33333333');
  expect(read).toHaveBeenCalledTimes(2); expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1); expect(screen.queryByText('Selected order')).toBeNull();
});

test('identity replacement clears loaded and selected A presentation in the layout commit before passive effects', async () => {
  const replacementList = deferred<unknown>();
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>()
    .mockResolvedValueOnce([view(merchantA, orderA)])
    .mockImplementationOnce(async () => replacementList.promise);
  const value = setup(read);
  let renderer!: SynchronousRenderer;
  await act(async () => { renderer = testRenderer.create(value.tree()); });
  expect(renderedText(renderer)).toContain('Order 33333333');
  await act(async () => { renderer.unstable_flushSync(() => renderer.root.findByProps({ accessibilityLabel: 'Order 33333333. Ready for pickup' }).props.onPress()); });
  expect(renderedText(renderer)).toContain('Selected order');
  const clearsBefore = value.pickup.clearInspection.mock.calls.length;
  value.replaceIdentity();
  await act(async () => {
    renderer.unstable_flushSync(() => renderer.update(value.tree()));
    expect(renderedText(renderer)).not.toContain('Order 33333333');
    expect(renderedText(renderer)).not.toContain('Selected order');
    expect(renderedText(renderer)).not.toContain('Pickup status');
  });
  expect(value.pickup.clearInspection).toHaveBeenCalledTimes(clearsBefore + 1);
  expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1);
  expect(read).toHaveBeenCalledTimes(2);
  await act(async () => { renderer.unmount(); });
});

test('identity replacement clears stale retained A list in the layout commit', async () => {
  const refresh = deferred<unknown>(); const replacementList = deferred<unknown>();
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>()
    .mockResolvedValueOnce([view(merchantA, orderA)])
    .mockImplementationOnce(async () => refresh.promise)
    .mockImplementationOnce(async () => replacementList.promise);
  const value = setup(read); let renderer!: SynchronousRenderer;
  await act(async () => { renderer = testRenderer.create(value.tree()); });
  await act(async () => { renderer.unstable_flushSync(() => renderer.root.findByProps({ accessibilityLabel: 'Refresh orders' }).props.onPress()); });
  expect(renderedText(renderer)).toContain('Order 33333333');
  expect(renderedText(renderer)).toContain('Showing earlier order information');
  value.replaceIdentity();
  await act(async () => {
    renderer.unstable_flushSync(() => renderer.update(value.tree()));
    expect(renderedText(renderer)).not.toContain('Order 33333333');
    expect(renderedText(renderer)).not.toContain('Showing earlier order information');
  });
  await act(async () => { renderer.unmount(); });
});

test('identity replacement aborts pending A list ownership and late A completion cannot publish', async () => {
  const pendingA = deferred<unknown>(); const pendingB = deferred<unknown>();
  const signals: AbortSignal[] = [];
  let requestCount = 0;
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async (_path, signal) => {
    if (signal) signals.push(signal);
    requestCount += 1;
    return requestCount === 1 ? pendingA.promise : pendingB.promise;
  });
  const value = setup(read); const mounted = await render(value.tree());
  expect(read).toHaveBeenCalledTimes(1); expect(signals[0].aborted).toBe(false);
  value.replaceIdentity(); await mounted.rerender(value.tree());
  expect(signals[0].aborted).toBe(true); expect(read).toHaveBeenCalledTimes(2);
  await act(async () => { pendingA.resolve([view(merchantA, orderA)]); await pendingA.promise; });
  expect(screen.queryByText('Order 33333333')).toBeNull(); expect(value.pickup.inspectOrder).not.toHaveBeenCalled();
  await act(async () => { pendingB.resolve([view(merchantA, orderB)]); await pendingB.promise; });
  expect(screen.getByText('Order 44444444')).toBeTruthy();
});

test('same merchant and exact continuity rerender preserves presentation without duplicate work', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read);
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333');
  await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  const clearsBefore = value.pickup.clearInspection.mock.calls.length;
  await mounted.rerender(value.tree());
  expect(screen.getByText('Selected order')).toBeTruthy(); expect(read).toHaveBeenCalledTimes(1);
  expect(value.pickup.clearInspection).toHaveBeenCalledTimes(clearsBefore); expect(value.pickup.inspectOrder).toHaveBeenCalledTimes(1);
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

test('actionable idle shows one localized ACK action; mount and non-actionable idle create no command work', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read);
  value.setAcknowledgement(Object.freeze({ status: 'idle' }), true);
  await render(value.tree()); await screen.findByText('Order 33333333');
  expect(value.acknowledgeArrival).not.toHaveBeenCalled(); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Acknowledge arrival')).toBeNull();
  await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('Courier has arrived')).toBeTruthy(); expect(screen.getByText('You can acknowledge the courier’s arrival now.')).toBeTruthy();
  expect(screen.getByLabelText('Acknowledge arrival')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText('Acknowledge arrival')); });
  expect(value.acknowledgeArrival).toHaveBeenCalledTimes(1); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
});

test('Strict Mode rehearsal creates no ACK or reconciliation work', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'idle' }), true);
  await render(value.tree(merchantA, 'Merchant A', true)); await screen.findByText('Order 33333333');
  expect(value.acknowledgeArrival).not.toHaveBeenCalled(); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
});

test('non-actionable idle and invalidated state fabricate no ACK control', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read);
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.queryByLabelText('Acknowledge arrival')).toBeNull();
  value.setAcknowledgement(Object.freeze({ status: 'invalidated', reason: 'scope_changed' }), true); await mounted.rerender(value.tree());
  expect(screen.queryByLabelText('Acknowledge arrival')).toBeNull(); expect(screen.queryByText(/scope_changed/)).toBeNull();
});

test('submitting and reconciling are disabled, restrained, and cannot duplicate invocation', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read);
  value.setAcknowledgement(Object.freeze({ status: 'submitting' })); const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByLabelText('Acknowledging arrival…').props.accessibilityState).toEqual({ disabled: true, busy: true });
  fireEvent.press(screen.getByLabelText('Acknowledging arrival…')); expect(value.acknowledgeArrival).not.toHaveBeenCalled();
  value.setAcknowledgement(Object.freeze({ status: 'reconciling' })); await mounted.rerender(value.tree());
  expect(screen.getByLabelText('Checking status…').props.accessibilityState).toEqual({ disabled: true, busy: true });
  fireEvent.press(screen.getByLabelText('Checking status…')); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
});

test('applied confirms arrival without another mutation or navigation action', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'applied' }));
  await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('Arrival acknowledged')).toBeTruthy(); expect(screen.getByText('The courier’s arrival has been confirmed.')).toBeTruthy(); expect(value.acknowledgeArrival).not.toHaveBeenCalled(); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
});

test('publication replacement presentation follows the locked capability and removes stale applied state', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA), view(merchantA, orderB)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'applied' }));
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('Arrival acknowledged')).toBeTruthy();
  value.setAcknowledgement(Object.freeze({ status: 'idle' }), false); await act(async () => { fireEvent.press(screen.getByLabelText('Order 44444444. Ready for pickup')); }); await mounted.rerender(value.tree());
  expect(screen.queryByText('Arrival acknowledged')).toBeNull(); expect(screen.queryByLabelText('Acknowledge arrival')).toBeNull(); expect(value.acknowledgeArrival).not.toHaveBeenCalled();
});

test('outcome unknown never claims success and offers explicit status check only under capability authority', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'outcome_unknown' }));
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('Confirmation not clear yet')).toBeTruthy(); expect(screen.getByText('AYO could not confirm the result. No action is available right now.')).toBeTruthy(); expect(screen.queryByText('Arrival acknowledged')).toBeNull(); expect(screen.queryByLabelText('Check status')).toBeNull(); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
  value.setAcknowledgement(Object.freeze({ status: 'outcome_unknown' }), false, true); await mounted.rerender(value.tree());
  expect(screen.getByText('AYO could not confirm the result. You can check the current status.')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText('Check status')); });
  expect(value.reconcileAcknowledgeArrival).toHaveBeenCalledTimes(1); expect(value.acknowledgeArrival).not.toHaveBeenCalled();
});

test('same-attempt retry is explicit and delegates only through the locked capability', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'retry_same_attempt' }), true);
  await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('You can retry the same acknowledgement safely.')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText('Try again')); });
  expect(value.acknowledgeArrival).toHaveBeenCalledTimes(1); expect(value.reconcileAcknowledgeArrival).not.toHaveBeenCalled();
});

test('rejected state is bounded, hides internal reason, and only retries when capability permits', async () => {
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'rejected', reason: 'temporarily_unavailable' }));
  const mounted = await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  expect(screen.getByText('Action not available right now')).toBeTruthy(); expect(screen.getByText('The arrival acknowledgement did not complete, and no action is available right now.')).toBeTruthy(); expect(screen.queryByText(/temporarily_unavailable|refresh_required/)).toBeNull(); expect(screen.queryByLabelText('Try again')).toBeNull();
  value.setAcknowledgement(Object.freeze({ status: 'rejected', reason: 'refresh_required' }), true); await mounted.rerender(value.tree());
  await act(async () => { fireEvent.press(screen.getByLabelText('Try again')); }); expect(value.acknowledgeArrival).toHaveBeenCalledTimes(1);
});

test('Amharic ACK copy resolves and visible command labels expose no authority identifiers', async () => {
  expect(merchantOperationalOrderCopy.am.acknowledgeArrival).toBe('መድረሱን አረጋግጥ');
  const read = jest.fn<Promise<unknown>, [string, AbortSignal?]>(async () => [view(merchantA, orderA)]); const value = setup(read); value.setAcknowledgement(Object.freeze({ status: 'idle' }), true);
  await render(value.tree()); await screen.findByText('Order 33333333'); await act(async () => { fireEvent.press(screen.getByLabelText('Order 33333333. Ready for pickup')); });
  const label = screen.getByLabelText('Acknowledge arrival').props.accessibilityLabel;
  expect(label).toBe('Acknowledge arrival'); for (const hidden of [merchantA, orderA, 'pickup', 'generation', 'version', 'attempt', 'key']) expect(label).not.toContain(hidden);
});
