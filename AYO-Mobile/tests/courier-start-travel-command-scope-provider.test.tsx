import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Pressable, Text, View } from 'react-native';
import { useLayoutEffect, useState } from 'react';

import { CourierStartTravelCommandScopeProvider, TrustedCourierHandoffStatus, useStartTravelAttemptCapability } from '@/contexts/courier-start-travel-command-scope';
import * as identitySessionContext from '@/contexts/identity-session';
import { IdentitySessionProvider, type IdentitySessionServices, useIdentityCommandRuntime, useIdentitySession } from '@/contexts/identity-session';
import { LanguageProvider } from '@/contexts/language';
import * as operationalContext from '@/contexts/operational-context';
import { OperationalContextProvider, useCourierCommandContext, useOperationalContext } from '@/contexts/operational-context';
import type { AuthenticatedSession } from '@/domain/auth-session';
import type { AuthenticationApi } from '@/services/authentication-api';
import { type CredentialStore, SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';
import type { StartTravelAttemptHandle } from '@/services/courier-start-travel-command-scope';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const session: AuthenticatedSession = {
  identityId, sessionId, identityKind: 'driver', accessToken: 'a'.repeat(64), refreshToken: 'r'.repeat(64),
  accessExpiresAt: '2099-01-01T01:00:00Z', refreshExpiresAt: '2099-01-02T00:00:00Z',
};
const pickupResponse = { pickup_id: pickupId, state: 'courier_assigned', version: 7, assigned_at: '2026-08-07T06:00:00Z', travelling_at: null, arrived_at: null, merchant_acknowledged_at: null, waiting_duration_seconds: null, terminal_reason: null, updated_at: '2026-08-07T06:00:00Z', presentation_action: 'start_travel' };

class MemoryStore implements CredentialStore {
  value: string | null = null;
  async get() { return this.value; }
  async set(_key: string, value: string) { this.value = value; }
  async remove() { this.value = null; }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((settle) => { resolve = settle; });
  return { promise, resolve };
}

type RetainedCapability = Readonly<{
  canCreateAttempt(): boolean;
  createAttempt(): StartTravelAttemptHandle | undefined;
}>;
let retainedCapability: RetainedCapability | undefined;
let retainedHandle: StartTravelAttemptHandle | undefined;
const readRetainedCapability = (): RetainedCapability | undefined => retainedCapability;
const readRetainedHandle = (): StartTravelAttemptHandle | undefined => retainedHandle;

function Consumer() {
  const publicIdentity = useIdentitySession();
  const commandIdentity = useIdentityCommandRuntime();
  const operational = useOperationalContext();
  const commandContext = useCourierCommandContext();
  const capability = useStartTravelAttemptCapability();
  const [created, setCreated] = useState('none');
  return <View>
    {operational.status === 'ready' ? <TrustedCourierHandoffStatus pickupId={pickupId} /> : null}
    <Text testID="identity-status">{publicIdentity.status}</Text>
    <Text testID="operational-status">{operational.status}</Text>
    <Text testID="operational-refreshing">{String(operational.refreshing)}</Text>
    <Text testID="identity-internals">{String('sessionId' in publicIdentity || 'identityGeneration' in publicIdentity)}</Text>
    <Text testID="operational-internals">{String('contextGeneration' in operational)}</Text>
    <Text testID="command-identity">{String(commandIdentity.readIdentity()?.identityGeneration ?? 'none')}</Text>
    <Text testID="command-context">{String(commandContext.readCourierContext()?.contextGeneration ?? 'none')}</Text>
    <Text testID="publisher-exposed">{String('publishFresh' in capability)}</Text>
    <Text testID="created">{created}</Text>
    <Pressable testID="create-current" onPress={() => { retainedCapability = capability; retainedHandle = capability.createAttempt(); setCreated(retainedHandle ? `${Object.keys(retainedHandle).join(',')}:${retainedHandle.isCurrent()}` : 'none'); }}><Text>Test creation</Text></Pressable>
    <Pressable testID="select-personal" onPress={() => operational.selectArea('personal')}><Text>Test selection</Text></Pressable>
    <Pressable testID="invalidate-courier" onPress={() => operational.invalidateCourier(pickupId)}><Text>Test invalidation</Text></Pressable>
  </View>;
}

function MinimalConsumer() {
  const capability = useStartTravelAttemptCapability();
  return <View>
    <TrustedCourierHandoffStatus pickupId={pickupId} />
    <Pressable testID="create-minimal" onPress={() => { retainedCapability = capability; retainedHandle = capability.createAttempt(); }}><Text>Test creation</Text></Pressable>
  </View>;
}

type ReplacementObservation = Readonly<{
  distinctCapability: boolean;
  oldHandleCurrent: boolean | undefined;
  oldCanCreate: boolean | undefined;
  oldCreate: StartTravelAttemptHandle | undefined;
}>;

function ReplacementObserver({ previousCapability, previousHandle, observe }: {
  previousCapability: RetainedCapability;
  previousHandle: StartTravelAttemptHandle;
  observe(value: ReplacementObservation): void;
}) {
  const capability = useStartTravelAttemptCapability();
  useLayoutEffect(() => {
    observe({
      distinctCapability: capability !== previousCapability,
      oldHandleCurrent: previousHandle.isCurrent(),
      oldCanCreate: previousCapability.canCreateAttempt(),
      oldCreate: previousCapability.createAttempt(),
    });
  }, [capability, observe, previousCapability, previousHandle]);
  return null;
}

function RemovalObserver({ previousCapability, previousHandle, observe }: {
  previousCapability: RetainedCapability;
  previousHandle: StartTravelAttemptHandle;
  observe(value: Omit<ReplacementObservation, 'distinctCapability'>): void;
}) {
  useLayoutEffect(() => {
    observe({
      oldHandleCurrent: previousHandle.isCurrent(),
      oldCanCreate: previousCapability.canCreateAttempt(),
      oldCreate: previousCapability.createAttempt(),
    });
  }, [observe, previousCapability, previousHandle]);
  return null;
}

test('mounted trusted provider derives an attempt without exposing raw scope or submitting', async () => {
  retainedCapability = undefined;
  retainedHandle = undefined;
  const store = new MemoryStore();
  const vault = new SecureSessionVault(store);
  await vault.save(session);
  const api = { activation: async () => ({ activated: true }), signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api);
  const contextRead = deferred<unknown>();
  let pickupReads = 0;
  const services: IdentitySessionServices = { api: Promise.resolve(api), manager: Promise.resolve(manager), read: async (path) => {
    if (path === '/api/mobile/context') return contextRead.promise;
    if (path.endsWith('/custody')) return { availability: 'not_started' };
    pickupReads += 1;
    if (pickupReads > 1) throw new Error('offline');
    return pickupResponse;
  } };
  await act(() => { render(<IdentitySessionProvider services={services}><OperationalContextProvider><CourierStartTravelCommandScopeProvider><LanguageProvider><Consumer /></LanguageProvider></CourierStartTravelCommandScopeProvider></OperationalContextProvider></IdentitySessionProvider>); });
  await waitFor(() => expect(screen.getByTestId('identity-status').props.children).toBe('authenticated'));
  await act(async () => { contextRead.resolve({ personal: { available: true }, merchants: [], courier: { pickup_id: pickupId, availability: 'current_pickup' } }); });
  await waitFor(() => { expect(screen.getByTestId('operational-status').props.children).toBe('ready'); expect(screen.getByTestId('operational-refreshing').props.children).toBe('false'); });
  expect(screen.getByTestId('created').props.children).toBe('none');
  expect(screen.getByTestId('identity-internals').props.children).toBe('false');
  expect(screen.getByTestId('operational-internals').props.children).toBe('false');
  expect(screen.getByTestId('publisher-exposed').props.children).toBe('false');
  expect(screen.getByTestId('command-identity').props.children).not.toBe('none');
  expect(screen.getByTestId('command-context').props.children).not.toBe('none');
  await waitFor(() => expect(screen.getByText('Pickup work is current')).toBeTruthy());
  await act(() => { fireEvent.press(screen.getByTestId('create-current')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('isCurrent:true'));
  const contextGeneration = screen.getByTestId('command-context').props.children;
  await act(() => { fireEvent.press(screen.getByTestId('select-personal')); });
  expect(screen.getByTestId('command-context').props.children).toBe(contextGeneration);
  await act(() => { fireEvent.press(screen.getByLabelText('Refresh')); });
  await waitFor(() => expect(screen.getByText('Information may be out of date')).toBeTruthy());
  await act(() => { fireEvent.press(screen.getByTestId('create-current')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('none'));
  await act(() => { fireEvent.press(screen.getByTestId('invalidate-courier')); fireEvent.press(screen.getByTestId('create-current')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('none'));
});

test('provider retirement invalidates retained capability and handle while identical replacement remains independent', async () => {
  retainedCapability = undefined;
  retainedHandle = undefined;

  async function mountProvider() {
    const store = new MemoryStore();
    const vault = new SecureSessionVault(store);
    await vault.save(session);
    const api = { activation: async () => ({ activated: true }), signOut: async () => undefined } as unknown as AuthenticationApi;
    const manager = new SessionManager(vault, api);
    const services: IdentitySessionServices = { api: Promise.resolve(api), manager: Promise.resolve(manager), read: async (path) => {
      if (path === '/api/mobile/context') return { personal: { available: true }, merchants: [], courier: { pickup_id: pickupId, availability: 'current_pickup' } };
      if (path.endsWith('/custody')) return { availability: 'not_started' };
      return pickupResponse;
    } };
    const mounted = render(<IdentitySessionProvider services={services}><OperationalContextProvider><CourierStartTravelCommandScopeProvider><LanguageProvider><Consumer /></LanguageProvider></CourierStartTravelCommandScopeProvider></OperationalContextProvider></IdentitySessionProvider>);
    await waitFor(() => expect(screen.getByTestId('identity-status').props.children).toBe('authenticated'));
    await waitFor(() => expect(screen.getByText('Pickup work is current')).toBeTruthy());
    await act(() => { fireEvent.press(screen.getByTestId('create-current')); });
    await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('isCurrent:true'));
    return mounted;
  }

  const providerA = await mountProvider();
  const capabilityA = readRetainedCapability(); const handleA = readRetainedHandle();
  expect(capabilityA).toBeDefined(); expect(handleA).toBeDefined();
  expect(handleA?.isCurrent()).toBe(true);
  await act(() => providerA.unmount());
  expect(handleA?.isCurrent()).toBe(false);
  expect(capabilityA?.canCreateAttempt()).toBe(false);
  expect(capabilityA?.createAttempt()).toBeUndefined();

  retainedCapability = undefined;
  retainedHandle = undefined;
  const providerB = await mountProvider();
  const handleB = readRetainedHandle();
  expect(handleA?.isCurrent()).toBe(false);
  expect(handleB).toBeDefined();
  expect(handleB?.isCurrent()).toBe(true);
  await act(() => providerB.unmount());
});

test('committed replacement and removal close old capabilities before the new tree is observable', async () => {
  retainedCapability = undefined;
  retainedHandle = undefined;
  const store = new MemoryStore();
  const vault = new SecureSessionVault(store);
  await vault.save(session);
  const api = { activation: async () => ({ activated: true }), signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api);
  const latePickup = deferred<unknown>();
  let pickupReads = 0;
  const services: IdentitySessionServices = { api: Promise.resolve(api), manager: Promise.resolve(manager), read: async (path) => {
    if (path === '/api/mobile/context') return { personal: { available: true }, merchants: [], courier: { pickup_id: pickupId, availability: 'current_pickup' } };
    if (path.endsWith('/custody')) return { availability: 'not_started' };
    pickupReads += 1;
    if (pickupReads === 2) return latePickup.promise;
    return pickupResponse;
  } };
  const tree = (key: string, child: React.ReactNode) => <IdentitySessionProvider key={key} services={services}><OperationalContextProvider><CourierStartTravelCommandScopeProvider><LanguageProvider>{child}</LanguageProvider></CourierStartTravelCommandScopeProvider></OperationalContextProvider></IdentitySessionProvider>;
  const mounted = await render(tree('A', <Consumer />));
  await waitFor(() => expect(screen.getByText('Pickup work is current')).toBeTruthy());
  await act(() => { fireEvent.press(screen.getByTestId('create-current')); });
  const capabilityA = readRetainedCapability(); const handleA = readRetainedHandle();
  expect(capabilityA).toBeDefined(); expect(handleA).toBeDefined(); expect(handleA?.isCurrent()).toBe(true);
  await act(() => { fireEvent.press(screen.getByLabelText('Refresh')); });
  expect(pickupReads).toBe(2);

  let observation: ReplacementObservation | undefined;
  await mounted.rerender(tree('B', <ReplacementObserver previousCapability={capabilityA!} previousHandle={handleA!} observe={(value) => { observation = value; }} />));
  expect(observation).toEqual({ distinctCapability: true, oldHandleCurrent: false, oldCanCreate: false, oldCreate: undefined });
  await act(async () => { latePickup.resolve(pickupResponse); });
  expect(handleA?.isCurrent()).toBe(false);

  retainedCapability = undefined;
  retainedHandle = undefined;
  await mounted.rerender(tree('B', <Consumer />));
  await waitFor(() => expect(screen.getByText('Pickup work is current')).toBeTruthy());
  await act(() => { fireEvent.press(screen.getByTestId('create-current')); });
  const capabilityB = readRetainedCapability(); const handleB = readRetainedHandle();
  expect(capabilityB).toBeDefined(); expect(handleB).toBeDefined(); expect(handleB?.isCurrent()).toBe(true);
  expect(handleA?.isCurrent()).toBe(false);

  let removal: Omit<ReplacementObservation, 'distinctCapability'> | undefined;
  await mounted.rerender(<RemovalObserver previousCapability={capabilityB!} previousHandle={handleB!} observe={(value) => { removal = value; }} />);
  expect(removal).toEqual({ oldHandleCurrent: false, oldCanCreate: false, oldCreate: undefined });
  await mounted.unmount();
});

test('reader dependency replacement closes scope A before scope B layout observation', async () => {
  retainedCapability = undefined;
  retainedHandle = undefined;
  const identityValue = { identityId, sessionId, identityGeneration: 1 };
  const courierValue = { pickupId, contextGeneration: 1, identityGeneration: 1 };
  let readIdentity = () => identityValue;
  let readCourierContext = () => courierValue;
  const authenticatedRead = async (path: string) => path.endsWith('/custody') ? { availability: 'not_started' } : pickupResponse;
  const operationalValue: ReturnType<typeof operationalContext.useOperationalContext> = {
    status: 'ready', areas: [], selected: undefined, chooserVisible: false, refreshing: false,
    refresh: async () => undefined, selectArea: () => undefined, showChooser: () => undefined, invalidateCourier: () => undefined,
  };
  const identitySpy = jest.spyOn(identitySessionContext, 'useIdentityCommandRuntime').mockImplementation(() => ({ readIdentity }));
  const readSpy = jest.spyOn(identitySessionContext, 'useAuthenticatedRead').mockImplementation(() => authenticatedRead);
  const courierSpy = jest.spyOn(operationalContext, 'useCourierCommandContext').mockImplementation(() => ({ readCourierContext }));
  const operationalSpy = jest.spyOn(operationalContext, 'useOperationalContext').mockImplementation(() => operationalValue);
  try {
    const tree = (child: React.ReactNode) => <CourierStartTravelCommandScopeProvider><LanguageProvider>{child}</LanguageProvider></CourierStartTravelCommandScopeProvider>;
    const mounted = await render(tree(<MinimalConsumer />));
    await waitFor(() => expect(screen.getByText('Pickup work is current')).toBeTruthy());
    await act(() => { fireEvent.press(screen.getByTestId('create-minimal')); });
    const capabilityA = readRetainedCapability(); const handleA = readRetainedHandle();
    expect(capabilityA).toBeDefined(); expect(handleA).toBeDefined(); expect(handleA?.isCurrent()).toBe(true);

    readIdentity = () => identityValue;
    readCourierContext = () => courierValue;
    let observation: ReplacementObservation | undefined;
    await mounted.rerender(tree(<ReplacementObserver previousCapability={capabilityA!} previousHandle={handleA!} observe={(value) => { observation = value; }} />));
    expect(observation).toEqual({ distinctCapability: true, oldHandleCurrent: false, oldCanCreate: false, oldCreate: undefined });
    await mounted.unmount();
  } finally {
    identitySpy.mockRestore(); readSpy.mockRestore(); courierSpy.mockRestore(); operationalSpy.mockRestore();
  }
});
