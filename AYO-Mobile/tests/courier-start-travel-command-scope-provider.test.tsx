import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Pressable, Text, View } from 'react-native';
import { useState } from 'react';

import { CourierStartTravelCommandScopeProvider, useStartTravelAttemptCapability, useStartTravelFreshEvidencePublisher } from '@/contexts/courier-start-travel-command-scope';
import { IdentitySessionProvider, type IdentitySessionServices, useIdentityCommandRuntime, useIdentitySession } from '@/contexts/identity-session';
import { OperationalContextProvider, useCourierCommandContext, useOperationalContext } from '@/contexts/operational-context';
import type { AuthenticatedSession } from '@/domain/auth-session';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import type { AuthenticationApi } from '@/services/authentication-api';
import { type CredentialStore, SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const session: AuthenticatedSession = {
  identityId, sessionId, identityKind: 'driver', accessToken: 'a'.repeat(64), refreshToken: 'r'.repeat(64),
  accessExpiresAt: '2099-01-01T01:00:00Z', refreshExpiresAt: '2099-01-02T00:00:00Z',
};
const handoff: CourierHandoffSnapshot = Object.freeze({ status: 'pickup_current', pickupVersion: 7, updatedAt: '2026-08-07T06:00:00Z', presentationAction: 'start_travel' });

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

function Consumer() {
  const publicIdentity = useIdentitySession();
  const commandIdentity = useIdentityCommandRuntime();
  const operational = useOperationalContext();
  const commandContext = useCourierCommandContext();
  const capability = useStartTravelAttemptCapability();
  const evidence = useStartTravelFreshEvidencePublisher();
  const [created, setCreated] = useState('none');
  return <View>
    <Text testID="identity-status">{publicIdentity.status}</Text>
    <Text testID="operational-status">{operational.status}</Text>
    <Text testID="operational-refreshing">{String(operational.refreshing)}</Text>
    <Text testID="identity-internals">{String('sessionId' in publicIdentity || 'identityGeneration' in publicIdentity)}</Text>
    <Text testID="operational-internals">{String('contextGeneration' in operational)}</Text>
    <Text testID="command-identity">{String(commandIdentity.readIdentity()?.identityGeneration ?? 'none')}</Text>
    <Text testID="command-context">{String(commandContext.readCourierContext()?.contextGeneration ?? 'none')}</Text>
    <Text testID="created">{created}</Text>
    <Pressable testID="publish-fresh" onPress={() => { evidence.publishFresh(pickupId, handoff); const attempt = capability.createAttempt(); setCreated(attempt ? `${attempt.pickupId}:${attempt.expectedVersion}` : 'none'); }}><Text>Test publication</Text></Pressable>
    <Pressable testID="create-current" onPress={() => { const attempt = capability.createAttempt(); setCreated(attempt ? `${attempt.pickupId}:${attempt.expectedVersion}` : 'none'); }}><Text>Test creation</Text></Pressable>
    <Pressable testID="clear-fresh" onPress={() => evidence.clearFresh(pickupId)}><Text>Test stale presentation</Text></Pressable>
    <Pressable testID="select-personal" onPress={() => operational.selectArea('personal')}><Text>Test selection</Text></Pressable>
    <Pressable testID="invalidate-courier" onPress={() => operational.invalidateCourier(pickupId)}><Text>Test invalidation</Text></Pressable>
  </View>;
}

test('mounted trusted provider derives an attempt without exposing raw scope or submitting', async () => {
  const store = new MemoryStore();
  const vault = new SecureSessionVault(store);
  await vault.save(session);
  const api = { activation: async () => ({ activated: true }), signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api);
  const contextRead = deferred<unknown>();
  const services: IdentitySessionServices = { api: Promise.resolve(api), manager: Promise.resolve(manager), read: async () => contextRead.promise };
  await act(() => { render(<IdentitySessionProvider services={services}><OperationalContextProvider><CourierStartTravelCommandScopeProvider><Consumer /></CourierStartTravelCommandScopeProvider></OperationalContextProvider></IdentitySessionProvider>); });
  await waitFor(() => expect(screen.getByTestId('identity-status').props.children).toBe('authenticated'));
  await act(async () => { contextRead.resolve({ personal: { available: true }, merchants: [], courier: { pickup_id: pickupId, availability: 'current_pickup' } }); });
  await waitFor(() => { expect(screen.getByTestId('operational-status').props.children).toBe('ready'); expect(screen.getByTestId('operational-refreshing').props.children).toBe('false'); });
  expect(screen.getByTestId('created').props.children).toBe('none');
  expect(screen.getByTestId('identity-internals').props.children).toBe('false');
  expect(screen.getByTestId('operational-internals').props.children).toBe('false');
  expect(screen.getByTestId('command-identity').props.children).not.toBe('none');
  expect(screen.getByTestId('command-context').props.children).not.toBe('none');
  await act(() => { fireEvent.press(screen.getByTestId('publish-fresh')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe(`${pickupId}:7`));
  const contextGeneration = screen.getByTestId('command-context').props.children;
  await act(() => { fireEvent.press(screen.getByTestId('select-personal')); });
  expect(screen.getByTestId('command-context').props.children).toBe(contextGeneration);
  await act(() => { fireEvent.press(screen.getByTestId('clear-fresh')); fireEvent.press(screen.getByTestId('create-current')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('none'));
  await act(() => { fireEvent.press(screen.getByTestId('publish-fresh')); });
  await act(() => { fireEvent.press(screen.getByTestId('invalidate-courier')); fireEvent.press(screen.getByTestId('create-current')); });
  await waitFor(() => expect(screen.getByTestId('created').props.children).toBe('none'));
});
