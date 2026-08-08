import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { CourierHandoffStatus, CourierMarkArrivedAction } from '@/components/courier-handoff-status';
import type { MarkArrivedPresentationCommand, StartTravelPresentationCommand } from '@/contexts/courier-start-travel-command-scope';
import { LanguageProvider } from '@/contexts/language';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { courierHandoffCopy } from '@/localization/courier-handoff-status';

const mockUseAuthenticatedRead = jest.fn();
const mockUseOperationalContext = jest.fn();
jest.mock('@/contexts/identity-session', () => ({
  ...jest.requireActual('@/contexts/identity-session'),
  useAuthenticatedRead: (...args: unknown[]) => mockUseAuthenticatedRead(...args),
}));
jest.mock('@/contexts/operational-context', () => ({
  ...jest.requireActual('@/contexts/operational-context'),
  useOperationalContext: (...args: unknown[]) => mockUseOperationalContext(...args),
}));

const pickupId = '33333333-3333-4333-8333-333333333333';
const markSnapshot = Object.freeze({ status: 'travelling', pickupVersion: 5, updatedAt: '2026-08-09T01:00:00Z', presentationAction: 'mark_arrived' }) satisfies CourierHandoffSnapshot;
const startSnapshot = Object.freeze({ ...markSnapshot, status: 'pickup_current' as const, presentationAction: 'start_travel' as const });
const noActionSnapshot = Object.freeze({ ...markSnapshot, presentationAction: 'none' as const });

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((settle) => { resolve = settle; });
  return { promise, resolve };
}

function command({ actionable = true, reconcilable = false, mark = async () => ({ outcome: 'applied' as const }), reconcile = async () => ({ outcome: 'applied' as const }) }: {
  actionable?: boolean;
  reconcilable?: boolean;
  mark?: MarkArrivedPresentationCommand['markArrived'];
  reconcile?: MarkArrivedPresentationCommand['reconcileMarkArrived'];
} = {}) {
  return Object.freeze({
    canMarkArrived: jest.fn(() => actionable),
    canReconcileMarkArrived: jest.fn(() => reconcilable),
    markArrived: jest.fn(mark),
    reconcileMarkArrived: jest.fn(reconcile),
  }) satisfies MarkArrivedPresentationCommand;
}

async function show(value: MarkArrivedPresentationCommand, options: Partial<React.ComponentProps<typeof CourierMarkArrivedAction>> = {}) {
  return render(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={value} copy={courierHandoffCopy.en} explicitRecoveryGeneration={0} interactionActive={false} operationalReady refreshing={false} snapshot={markSnapshot} viewStatus="fresh" {...options} />);
}

test('MARK is visible only with fresh exact evidence and bounded actionability', async () => {
  const cases: Array<Partial<React.ComponentProps<typeof CourierMarkArrivedAction>>> = [
    { snapshot: undefined }, { snapshot: startSnapshot }, { snapshot: noActionSnapshot }, { viewStatus: 'loading' },
    { viewStatus: 'stale' }, { viewStatus: 'unavailable' }, { viewStatus: 'malformed' },
    { viewStatus: 'conflicting' }, { refreshing: true }, { operationalReady: false }, { interactionActive: true },
  ];
  for (const props of cases) {
    const mounted = await show(command(), props);
    expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
    await mounted.unmount();
  }
  const denied = await show(command({ actionable: false }));
  expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
  await denied.unmount();
  const allowed = await show(command());
  expect(screen.getByLabelText(courierHandoffCopy.en.markArrived).props).toMatchObject({ accessibilityRole: 'button', accessibilityState: { disabled: false } });
  await allowed.unmount();
});

test('one explicit press invokes only the bounded facade and rapid presses remain one flight', async () => {
  const gate = deferred<{ outcome: 'applied' }>();
  const value = command({ mark: () => gate.promise });
  const mounted = await show(value);
  const button = screen.getByLabelText(courierHandoffCopy.en.markArrived);
  await act(() => { fireEvent.press(button); fireEvent.press(button); });
  expect(value.markArrived).toHaveBeenCalledTimes(1);
  expect(value.reconcileMarkArrived).not.toHaveBeenCalled();
  expect(screen.getByLabelText(courierHandoffCopy.en.markingArrival).props.accessibilityState).toEqual({ disabled: true });
  await act(async () => gate.resolve({ outcome: 'applied' }));
  expect(screen.getByText(courierHandoffCopy.en.arrivalConfirmed)).toBeTruthy();
  expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
  expect(JSON.stringify(mounted.toJSON())).not.toMatch(/GPS|location verified|physical location/i);
});

test('outcome unknown never resends and Check Status follows deterministic reconciliation availability', async () => {
  let reconcilable = false;
  const value = Object.freeze({
    canMarkArrived: jest.fn(() => false),
    canReconcileMarkArrived: jest.fn(() => reconcilable),
    markArrived: jest.fn(async () => { reconcilable = true; return { outcome: 'outcome_unknown' as const }; }),
    reconcileMarkArrived: jest.fn(async () => ({ outcome: 'applied' as const })),
  }) satisfies MarkArrivedPresentationCommand;
  const mounted = await show(value, { command: Object.freeze({ ...value, canMarkArrived: jest.fn(() => true) }) });
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.markArrived)));
  expect(screen.getByText(courierHandoffCopy.en.arrivalOutcomeUnknown)).toBeTruthy();
  expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
  expect(screen.getByLabelText(courierHandoffCopy.en.checkStatus)).toBeTruthy();
  await mounted.rerender(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={Object.freeze({ ...value, canReconcileMarkArrived: () => false })} copy={courierHandoffCopy.en} explicitRecoveryGeneration={0} interactionActive={false} operationalReady refreshing={false} snapshot={markSnapshot} viewStatus="fresh" />);
  expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();
  expect(value.markArrived).toHaveBeenCalledTimes(1);
});

test('presentation remount recovers ambiguous custody solely from canReconcileMarkArrived', async () => {
  const value = command({ actionable: false, reconcilable: true });
  const first = await show(value);
  expect(screen.getByLabelText(courierHandoffCopy.en.checkStatus)).toBeTruthy();
  expect(screen.getByText(courierHandoffCopy.en.arrivalOutcomeUnknown)).toBeTruthy();
  await first.unmount();
  await show(value);
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)));
  expect(value.reconcileMarkArrived).toHaveBeenCalledTimes(1);
  expect(value.markArrived).not.toHaveBeenCalled();
});

test('reconciliation is explicit and maps applied, retry, supersession, and bounded failures without enums', async () => {
  let actionable = false;
  let reconcilable = true;
  const retry = Object.freeze({
    canMarkArrived: jest.fn(() => actionable), canReconcileMarkArrived: jest.fn(() => reconcilable),
    markArrived: jest.fn(async () => ({ outcome: 'applied' as const })),
    reconcileMarkArrived: jest.fn(async () => { reconcilable = false; actionable = true; return { outcome: 'retry_same_attempt' as const }; }),
  }) satisfies MarkArrivedPresentationCommand;
  const mounted = await show(retry);
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)));
  expect(screen.getByText(courierHandoffCopy.en.arrivalRetryReady)).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.retryMarkArrived)));
  expect(retry.markArrived).toHaveBeenCalledTimes(1);

  actionable = false;
  await mounted.rerender(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={retry} copy={courierHandoffCopy.en} explicitRecoveryGeneration={0} interactionActive={false} operationalReady refreshing={false} snapshot={markSnapshot} viewStatus="fresh" />);
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryMarkArrived)).toBeNull();

  for (const result of [
    { outcome: 'invalidated' as const, reason: 'authority_lost' as const },
    { outcome: 'rejected' as const, reason: 'malformed_response' as const },
    { outcome: 'rejected' as const, reason: 'version_conflict' as const },
  ]) {
    const failure = command({ mark: async () => result });
    const view = await show(failure);
    await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.markArrived)));
    expect(JSON.stringify(view.toJSON())).not.toContain(result.reason);
    expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
    await view.unmount();
  }
});

test('unexpected throw fails closed and one successful explicit Refresh generation clears stale local copy only', async () => {
  let actionable = true;
  const value = Object.freeze({
    canMarkArrived: jest.fn(() => actionable), canReconcileMarkArrived: jest.fn(() => false),
    markArrived: jest.fn(async () => { actionable = false; throw new Error('unexpected'); }),
    reconcileMarkArrived: jest.fn(async () => ({ outcome: 'rejected' as const, reason: 'reconciliation_not_available' as const })),
  }) satisfies MarkArrivedPresentationCommand;
  const mounted = await show(value);
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.markArrived)));
  expect(screen.getByText(courierHandoffCopy.en.genericCommandFailure)).toBeTruthy();
  expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
  actionable = true;
  await mounted.rerender(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={value} copy={courierHandoffCopy.en} explicitRecoveryGeneration={1} interactionActive={false} operationalReady refreshing={false} snapshot={markSnapshot} viewStatus="fresh" />);
  await waitFor(() => expect(screen.queryByText(courierHandoffCopy.en.genericCommandFailure)).toBeNull());
  expect(screen.getByLabelText(courierHandoffCopy.en.markArrived)).toBeTruthy();
});

test('successful Refresh clears stale MARK presentation and follows ARRIVED, WAITING, none, or newer actionable truth', async () => {
  let actionable = true;
  let reconcilable = false;
  const value = Object.freeze({
    canMarkArrived: jest.fn(() => actionable), canReconcileMarkArrived: jest.fn(() => reconcilable),
    markArrived: jest.fn(async () => { actionable = false; reconcilable = true; return { outcome: 'outcome_unknown' as const }; }),
    reconcileMarkArrived: jest.fn(async () => ({ outcome: 'applied' as const })),
  }) satisfies MarkArrivedPresentationCommand;
  const mounted = await show(value);
  await act(async () => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.markArrived)));
  expect(screen.getByText(courierHandoffCopy.en.arrivalOutcomeUnknown)).toBeTruthy();

  for (const next of [
    { ...markSnapshot, status: 'at_merchant' as const, pickupVersion: 6, presentationAction: 'none' as const },
    { ...markSnapshot, status: 'waiting_for_merchant' as const, pickupVersion: 7, presentationAction: 'none' as const },
    noActionSnapshot,
  ]) {
    reconcilable = false;
    await mounted.rerender(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={value} copy={courierHandoffCopy.en} explicitRecoveryGeneration={next.pickupVersion} interactionActive={false} operationalReady refreshing={false} snapshot={next} viewStatus="fresh" />);
    expect(screen.queryByLabelText(courierHandoffCopy.en.markArrived)).toBeNull();
    expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();
    expect(screen.queryByText(courierHandoffCopy.en.arrivalOutcomeUnknown)).toBeNull();
  }

  actionable = true;
  const newer = { ...markSnapshot, pickupVersion: 8 };
  await mounted.rerender(<CourierMarkArrivedAction beginCommandInteraction={() => () => undefined} command={value} copy={courierHandoffCopy.en} explicitRecoveryGeneration={8} interactionActive={false} operationalReady refreshing={false} snapshot={newer} viewStatus="fresh" />);
  expect(screen.getByLabelText(courierHandoffCopy.en.markArrived)).toBeTruthy();
});

test('MARK enters the shared screen command lock and blocks Refresh without exposing custody', async () => {
  const gate = deferred<{ outcome: 'applied' }>();
  const mark = command({ mark: () => gate.promise });
  const start = Object.freeze({ canStartTravel: () => false, startTravel: async () => ({ outcome: 'invalidated' as const, reason: 'scope_changed' as const }), reconcileStartTravel: async () => ({ outcome: 'rejected' as const, reason: 'reconciliation_not_available' as const }) }) satisfies StartTravelPresentationCommand;
  const pickup = { pickup_id: pickupId, state: 'travelling_to_merchant', version: 5, assigned_at: '2026-08-09T00:00:00Z', travelling_at: '2026-08-09T00:30:00Z', arrived_at: null, merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: '2026-08-09T01:00:00Z', presentation_action: 'mark_arrived' };
  mockUseAuthenticatedRead.mockReturnValue(async (path: string) => path.endsWith('/custody') ? { availability: 'not_started' } : pickup);
  mockUseOperationalContext.mockReturnValue({ status: 'ready', areas: [], selected: undefined, chooserVisible: false, refreshing: false, refresh: async () => undefined, selectArea: () => undefined, showChooser: () => undefined, invalidateCourier: () => undefined });
  const mounted = await render(<LanguageProvider><CourierHandoffStatus pickupId={pickupId} commandEvidence={{ publishFresh: jest.fn(), clearFresh: jest.fn(), isUnexpectedStartFailureLatched: () => false }} markArrivedCommand={mark} startTravelCommand={start} /></LanguageProvider>);
  await screen.findByLabelText(courierHandoffCopy.en.markArrived);
  await act(() => fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.markArrived)));
  expect(screen.getByLabelText(courierHandoffCopy.en.refresh).props.accessibilityState).toMatchObject({ disabled: true });
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(mark.markArrived).toHaveBeenCalledTimes(1);
  await act(async () => gate.resolve({ outcome: 'applied' }));
  await waitFor(() => expect(screen.getByLabelText(courierHandoffCopy.en.refresh).props.accessibilityState).toMatchObject({ disabled: false }));
  await mounted.unmount();
});

test('EN and AM MARK keys remain exact and product copy never exposes command authority or physical proof', () => {
  expect(Object.keys(courierHandoffCopy.en)).toEqual(Object.keys(courierHandoffCopy.am));
  const rendered = Object.values(courierHandoffCopy).flatMap(Object.values).join(' ');
  for (const forbidden of ['idempotencyKey', 'expectedVersion', 'scope_changed', 'authority_lost', 'state_changed', 'GPS verified', 'physical location']) expect(rendered).not.toContain(forbidden);
});
