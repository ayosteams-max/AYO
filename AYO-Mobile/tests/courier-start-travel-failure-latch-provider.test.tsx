import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { useState } from 'react';
import { Pressable, Text } from 'react-native';

import { CourierStartTravelCommandInfrastructureProvider, TrustedCourierHandoffStatus } from '@/contexts/courier-start-travel-command-scope';
import { LanguageProvider } from '@/contexts/language';
import { StartTravelOutcomeUnknownError } from '@/domain/courier-start-travel-command';
import { courierHandoffCopy } from '@/localization/courier-handoff-status';

const mockUseAuthenticatedRead = jest.fn();
const mockUseOperationalContext = jest.fn();
const mockUseCourierCommandContext = jest.fn();
jest.mock('@/contexts/identity-session', () => ({
  ...jest.requireActual('@/contexts/identity-session'),
  useAuthenticatedRead: (...args: unknown[]) => mockUseAuthenticatedRead(...args),
}));
jest.mock('@/contexts/operational-context', () => ({
  ...jest.requireActual('@/contexts/operational-context'),
  useOperationalContext: (...args: unknown[]) => mockUseOperationalContext(...args),
  useCourierCommandContext: (...args: unknown[]) => mockUseCourierCommandContext(...args),
}));

const pickupId = '33333333-3333-4333-8333-333333333333';
const pickupResponse = Object.freeze({ pickup_id: pickupId, state: 'courier_assigned', version: 4, assigned_at: '2026-08-08T01:00:00Z', travelling_at: null, arrived_at: null, merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: '2026-08-08T01:00:00Z', presentation_action: 'start_travel' });
const noActionResponse = Object.freeze({ ...pickupResponse, state: 'travelling_to_merchant', version: 5, travelling_at: '2026-08-08T01:01:00Z', updated_at: '2026-08-08T01:01:00Z', presentation_action: 'mark_arrived' });

test('unexpected START failure survives remount and failed Refresh until a successful explicit Refresh', async () => {
  let pickupReads = 0;
  let nextResponse: unknown = pickupResponse;
  const read = jest.fn(async (path: string) => {
    if (path.endsWith('/custody')) return { availability: 'not_started' };
    pickupReads += 1;
    if (pickupReads === 3) throw new Error('offline');
    return nextResponse;
  });
  const identity = Object.freeze({
    readIdentity: () => Object.freeze({ identityId: '11111111-1111-4111-8111-111111111111', sessionId: '22222222-2222-4222-8222-222222222222', identityGeneration: 1 }),
    createStartTravelCommandService: jest.fn(async () => { throw new Error('unexpected command failure'); }),
  });
  const courier = Object.freeze({ pickupId, contextGeneration: 1, identityContinuity: Object.freeze({ isCurrent: () => true }) });
  mockUseAuthenticatedRead.mockReturnValue(read);
  mockUseCourierCommandContext.mockReturnValue({ readCourierContext: () => courier });
  mockUseOperationalContext.mockReturnValue({
    status: 'ready', areas: [], selected: undefined, chooserVisible: false, refreshing: false,
    refresh: async () => undefined, selectArea: () => undefined, showChooser: () => undefined, invalidateCourier: () => undefined,
  });

  function Harness() {
    const [generation, setGeneration] = useState(0);
    return <>
      <TrustedCourierHandoffStatus key={generation} pickupId={pickupId} />
      <Pressable testID="remount-handoff" onPress={() => setGeneration((value) => value + 1)}><Text>Remount Handoff</Text></Pressable>
    </>;
  }

  const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={identity}><LanguageProvider><Harness /></LanguageProvider></CourierStartTravelCommandInfrastructureProvider>);
  await screen.findByLabelText(courierHandoffCopy.en.startTravel);
  expect(pickupReads).toBe(1);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  expect(identity.createStartTravelCommandService).toHaveBeenCalledTimes(1);
  expect(screen.getByText(courierHandoffCopy.en.genericCommandFailure)).toBeTruthy();
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();

  await act(() => { fireEvent.press(screen.getByTestId('remount-handoff')); });
  await waitFor(() => expect(pickupReads).toBe(2));
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();
  expect(identity.createStartTravelCommandService).toHaveBeenCalledTimes(1);

  fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.refresh));
  await waitFor(() => expect(pickupReads).toBe(3));
  await waitFor(() => expect(screen.getByLabelText(courierHandoffCopy.en.refresh).props.accessibilityState).toMatchObject({ disabled: false }));
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();

  fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.refresh));
  await waitFor(() => expect(pickupReads).toBe(4));
  await screen.findByLabelText(courierHandoffCopy.en.startTravel);
  expect(identity.createStartTravelCommandService).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(courierHandoffCopy.en.genericCommandFailure)).toBeNull();
  expect(JSON.stringify(mounted.toJSON())).not.toContain('unexpected command failure');

  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  await waitFor(() => expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull());
  expect(identity.createStartTravelCommandService).toHaveBeenCalledTimes(1);
  nextResponse = noActionResponse;
  fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.refresh));
  await waitFor(() => expect(pickupReads).toBe(5));
  await waitFor(() => expect(screen.getByText(courierHandoffCopy.en.travelling)).toBeTruthy());
  expect(screen.queryByText(courierHandoffCopy.en.genericCommandFailure)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.retryStartTravel)).toBeNull();
  expect(screen.queryByLabelText(courierHandoffCopy.en.checkStatus)).toBeNull();
  await mounted.unmount();
});

test('remount preserves Check Status for controller-owned outcome unknown', async () => {
  let pickupReads = 0;
  const read = jest.fn(async (path: string) => {
    if (path.endsWith('/custody')) return { availability: 'not_started' };
    pickupReads += 1;
    return pickupResponse;
  });
  const identity = Object.freeze({
    readIdentity: () => Object.freeze({ identityId: '11111111-1111-4111-8111-111111111111', sessionId: '22222222-2222-4222-8222-222222222222', identityGeneration: 1 }),
    createStartTravelCommandService: jest.fn(async () => Object.freeze({
      submit: async () => { throw new StartTravelOutcomeUnknownError(); },
      reconcile: async () => Object.freeze({ outcome: 'retry_same_attempt' as const, pickup: Object.freeze({ pickupId, state: 'courier_assigned' as const, version: 4, updatedAt: '2026-08-08T01:00:00Z', presentationAction: 'start_travel' as const }) }),
    }) as never),
  });
  const courier = Object.freeze({ pickupId, contextGeneration: 1, identityContinuity: Object.freeze({ isCurrent: () => true }) });
  mockUseAuthenticatedRead.mockReturnValue(read);
  mockUseCourierCommandContext.mockReturnValue({ readCourierContext: () => courier });
  mockUseOperationalContext.mockReturnValue({
    status: 'ready', areas: [], selected: undefined, chooserVisible: false, refreshing: false,
    refresh: async () => undefined, selectArea: () => undefined, showChooser: () => undefined, invalidateCourier: () => undefined,
  });

  function Harness() {
    const [generation, setGeneration] = useState(0);
    return <>
      <TrustedCourierHandoffStatus key={generation} pickupId={pickupId} />
      <Pressable testID="remount-handoff-unknown" onPress={() => setGeneration((value) => value + 1)}><Text>Remount Unknown Handoff</Text></Pressable>
    </>;
  }

  const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={identity}><LanguageProvider><Harness /></LanguageProvider></CourierStartTravelCommandInfrastructureProvider>);
  await screen.findByLabelText(courierHandoffCopy.en.startTravel);
  await act(async () => { fireEvent.press(screen.getByLabelText(courierHandoffCopy.en.startTravel)); });
  expect(screen.getByLabelText(courierHandoffCopy.en.checkStatus)).toBeTruthy();
  await act(() => { fireEvent.press(screen.getByTestId('remount-handoff-unknown')); });
  await waitFor(() => expect(pickupReads).toBe(2));
  expect(screen.queryByLabelText(courierHandoffCopy.en.startTravel)).toBeNull();
  expect(screen.getByLabelText(courierHandoffCopy.en.checkStatus)).toBeTruthy();
  expect(identity.createStartTravelCommandService).toHaveBeenCalledTimes(1);
  await mounted.unmount();
});
