import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { CourierStartTravelAction } from '@/components/courier-handoff-status';
import type { StartTravelPresentationCommand } from '@/contexts/courier-start-travel-command-scope';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { courierHandoffCopy } from '@/localization/courier-handoff-status';

const snapshot = Object.freeze({
  status: 'pickup_current', pickupVersion: 4, updatedAt: '2026-08-08T01:00:00Z', presentationAction: 'start_travel',
}) satisfies CourierHandoffSnapshot;
const noAction = Object.freeze({ ...snapshot, status: 'travelling' as const, presentationAction: 'none' as const });

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((settle) => { resolve = settle; });
  return { promise, resolve };
}

function command({ actionable = true, start = async () => ({ outcome: 'applied' as const }), reconcile = async () => ({ outcome: 'outcome_unknown' as const }) }: {
  actionable?: boolean;
  start?: StartTravelPresentationCommand['startTravel'];
  reconcile?: StartTravelPresentationCommand['reconcileStartTravel'];
} = {}) {
  return Object.freeze({
    canStartTravel: jest.fn(() => actionable),
    startTravel: jest.fn(start),
    reconcileStartTravel: jest.fn(reconcile),
  }) satisfies StartTravelPresentationCommand;
}

async function show(value: StartTravelPresentationCommand, options: Partial<React.ComponentProps<typeof CourierStartTravelAction>> = {}) {
  return render(<CourierStartTravelAction command={value} copy={courierHandoffCopy.en} operationalReady refreshing={false} snapshot={snapshot} viewStatus="fresh" {...options} />);
}

test('START is visible only for fresh server action evidence plus bounded actionability', async () => {
  const cases: Array<Partial<React.ComponentProps<typeof CourierStartTravelAction>>> = [
    { snapshot: undefined }, { viewStatus: 'loading' }, { viewStatus: 'stale' }, { viewStatus: 'unavailable' },
    { viewStatus: 'malformed' }, { viewStatus: 'conflicting' }, { snapshot: noAction }, { refreshing: true }, { operationalReady: false },
  ];
  for (const props of cases) {
    const mounted = await show(command(), props);
    expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
    await mounted.unmount();
  }
  const unavailable = await show(command({ actionable: false }));
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  await unavailable.unmount();
  const available = await show(command());
  expect(screen.getByLabelText(courierHandoffCopy.en.startTravel).props.accessibilityRole).toBe('button');
  await available.unmount();
});

test('one press calls only the bounded facade and pending state blocks a rapid second invocation', async () => {
  const gate = deferred<{ outcome: 'applied' }>();
  const value = command({ start: () => gate.promise });
  await show(value);
  const start = screen.getByLabelText(courierHandoffCopy.en.startTravel);
  await act(() => { fireEvent.press(start); fireEvent.press(start); });
  expect(value.reconcileStartTravel).not.toHaveBeenCalled();
  expect(screen.getByLabelText(courierHandoffCopy.en.startingTravel).props.accessibilityState).toEqual({ disabled: true });
  await act(async () => { gate.resolve({ outcome: 'applied' }); });
  expect(screen.getByText(courierHandoffCopy.en.startConfirmedHelp)).toBeTruthy();
  expect(screen.queryByText(courierHandoffCopy.en.travelling)).toBeNull();
});

test('unknown outcome hides START and explicit status checks never call start', async () => {
  const reconcileGate = deferred<{ outcome: 'outcome_unknown' }>();
  let actionable = true;
  const value = Object.freeze({
    canStartTravel: jest.fn(() => actionable),
    startTravel: jest.fn(async () => { actionable = false; return { outcome: 'outcome_unknown' as const }; }),
    reconcileStartTravel: jest.fn(() => reconcileGate.promise),
  }) satisfies StartTravelPresentationCommand;
  await show(value);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.getByText(courierHandoffCopy.en.outcomeUnknown)).toBeTruthy();
  expect(screen.getByText(courierHandoffCopy.en.outcomeUnknownHelp)).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)); });
  expect(value.reconcileStartTravel).toHaveBeenCalledTimes(1);
  expect(value.startTravel).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText(courierHandoffCopy.en.checkingStatus).props.accessibilityState).toEqual({ disabled: true });
  await act(async () => { reconcileGate.resolve({ outcome: 'outcome_unknown' }); });
  expect(value.startTravel).toHaveBeenCalledTimes(1);
});

test('authoritative reconciliation alone exposes same-request retry and applied reconciliation removes it', async () => {
  const retrying = command({ start: async () => ({ outcome: 'outcome_unknown' }), reconcile: async () => ({ outcome: 'retry_same_attempt' }) });
  const retryMount = await show(retrying);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)); });
  expect(screen.getByText(courierHandoffCopy.en.retryReady)).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.retryStartTravel)); });
  expect(retrying.startTravel).toHaveBeenCalledTimes(2);
  await retryMount.unmount();

  const applied = command({ start: async () => ({ outcome: 'outcome_unknown' }), reconcile: async () => ({ outcome: 'applied' }) });
  await show(applied);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)); });
  expect(screen.getByText(courierHandoffCopy.en.startConfirmed)).toBeTruthy();
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
});

test('stale retry, definitive failures, and unavailable reconciliation fail closed without technical copy', async () => {
  const outcomes = [
    { outcome: 'invalidated' as const, reason: 'authority_lost' as const },
    { outcome: 'invalidated' as const, reason: 'scope_changed' as const },
    { outcome: 'invalidated' as const, reason: 'state_changed' as const },
    { outcome: 'rejected' as const, reason: 'refresh_required' as const },
    { outcome: 'rejected' as const, reason: 'version_conflict' as const },
    { outcome: 'rejected' as const, reason: 'transition_not_allowed' as const },
    { outcome: 'rejected' as const, reason: 'malformed_response' as const },
    { outcome: 'rejected' as const, reason: 'reconciliation_not_available' as const },
  ];
  for (const outcome of outcomes) {
    const value = command({ start: async () => outcome });
    const mounted = await show(value);
    await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
    expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
    expect(JSON.stringify(mounted.toJSON())).not.toContain(outcome.reason);
    await mounted.unmount();
  }
  let actionable = true;
  const stale = Object.freeze({ canStartTravel: jest.fn(() => actionable), startTravel: jest.fn(async () => ({ outcome: 'outcome_unknown' as const })), reconcileStartTravel: jest.fn(async () => ({ outcome: 'retry_same_attempt' as const })) }) satisfies StartTravelPresentationCommand;
  await show(stale);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  actionable = false;
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)); });
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
  expect(screen.getByText(courierHandoffCopy.en.currentWorkChanged)).toBeTruthy();
});

test('remount-like missing local result offers neutral reconciliation without fabricating START', async () => {
  const value = command({ actionable: false, reconcile: async () => ({ outcome: 'rejected' as const, reason: 'reconciliation_not_available' as const }) });
  await show(value);
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.checkStatus)); });
  expect(value.reconcileStartTravel).toHaveBeenCalledTimes(1);
  expect(value.startTravel).not.toHaveBeenCalled();
});

test('English and Amharic command keys are aligned and no technical reason is user copy', () => {
  expect(Object.keys(courierHandoffCopy.en)).toEqual(Object.keys(courierHandoffCopy.am));
  const rendered = Object.values(courierHandoffCopy).flatMap(Object.values).join(' ');
  for (const reason of ['outcome_unknown', 'retry_same_attempt', 'scope_changed', 'authority_lost', 'state_changed', 'refresh_required', 'malformed_response', 'reconciliation_not_available']) {
    expect(rendered).not.toContain(reason);
  }
});
